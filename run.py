# encoding: utf-8
from flask import Flask, request, Response, render_template, jsonify
from twilio.rest import Client
from twilio.jwt.taskrouter.capabilities import WorkerCapabilityToken
from twilio.twiml.voice_response import VoiceResponse, Conference, Enqueue, Dial
from twilio.twiml.messaging_response import Message, MessagingResponse

from twilio.jwt.client import ClientCapabilityToken
from twilio.jwt.access_token import AccessToken
from twilio.jwt.access_token.grants import (ChatGrant, SyncGrant)

import os,json

app = Flask(__name__, static_folder='app/static')

# Your Account Sid and Auth Token from twilio.com/user/account
account_sid = os.environ.get("TWILIO_ACME_ACCOUNT_SID")
auth_token = os.environ.get("TWILIO_ACME_AUTH_TOKEN")

workspace_sid = os.environ.get("TWILIO_ACME_WORKSPACE_SID")  # workspace

workflow_sid = os.environ.get("TWILIO_ACME_SUPPORT_WORKFLOW_SID")  # support workflow
workflow_sales_sid = os.environ.get("TWILIO_ACME_SALES_WORKFLOW_SID")  # sales workflow
workflow_billing_sid = os.environ.get("TWILIO_ACME_BILLING_WORKFLOW_SID")  # billing workflow
workflow_OOO_sid = os.environ.get("TWILIO_ACME_OOO_SID")  # out of office workflow
workflow_mngr = os.environ.get("TWILIO_ACME_MANAGER_WORKFLOW_SID")  # manager escalation workflow


api_key = os.environ.get("TWILIO_ACME_CHAT_API_KEY")
api_secret = os.environ.get("TWILIO_ACME_CHAT_SECRET")

chat_service = os.environ.get("TWILIO_ACME_CHAT_SERVICE_SID")
sync_service = os.environ.get("TWILIO_ACME_SYNC_SERVICE_SID")

twiml_app = os.environ.get("TWILIO_ACME_TWIML_APP_SID")  # Twilio client application SID

caller_id = os.environ.get("TWILIO_ACME_CALLERID")  # Contact Center's phone number to be used in outbound communication
caller_id_sms = os.environ.get("TWILIO_ACME_SMS_NUMBER")

client = Client(account_sid, auth_token)

# Create dictionary with activity SIDs to be shared with the agent desktop
activity = {}

activities = client.taskrouter.workspaces(workspace_sid).activities.list()

for a in activities:
    activity[a.friendly_name] = a.sid


# private functions

def return_work_space(digits):
    # query user input and assign the correct workflow

    digit_pressed = digits
    if digit_pressed == "1":
        department = "sales"
        work_flow_sid = workflow_sales_sid
        workflowdata = (work_flow_sid, department)  # tuple

        return workflowdata

    if digit_pressed == "2":
        department = "support"
        work_flow_sid = workflow_sid
        workflowdata = (work_flow_sid, department)  # tuple

        return workflowdata

    if digit_pressed == "3":
        department = "billing"
        work_flow_sid = workflow_billing_sid
        workflowdata = (work_flow_sid, department)  # tuple

        return workflowdata


# create a new chat user

def create_sms_chat_user(identity):
    new_user = client.chat.services(chat_service).users.create(
        identity=identity
    )
    return new_user


# create a new chat channel

def create_channel(user):
    # create new channel
    print('new user, creating channel and user')

    new_sms_user_channel = client.chat.services(chat_service).channels.create(
        friendly_name=user.identity + ' support request')

    member = client.chat.services(chat_service).channels(new_sms_user_channel.sid).members.create(
        user.identity)

    return new_sms_user_channel


# Render index

def createSmsTask(from_user, body, channel):


    attributes = '{"selected_product":"sms", "product":"chat", "from": "' + \
                 from_user + '", "body":"' + body + \
                 '", "channel":"' + channel + '"}'
    task = client.taskrouter.workspaces(workspace_sid).tasks.create(workflow_sid=workflow_sid,
                                                                    task_channel='SMS',
                                                                    attributes=attributes)
    sendMessageToChannel(channel, from_user, body)


def sendMessageToChannel(channel, from_, content):
    client.chat.services(chat_service).channels(channel).messages.create(from_=from_, body=content)


@app.route("/", methods=['GET', 'POST'])
def hello_world():
    return render_template('index.html')


# Default route for support line voice request url
# Gather to select language

@app.route("/incoming_call", methods=['GET', 'POST'])
def incoming_call():
    resp = VoiceResponse()
    with resp.gather(num_digits="1", action="/incoming_call/department", timeout=10) as g:
        g.say("Para Espanol oprime el uno.", language='es')
        g.say("For English, press two.", language='en')
        g.say(u"Pour Francais, pressé trois", language='fr')

    return Response(str(resp), mimetype='text/xml')


##################################################################

# redirect the user to the correct department for their language choice

@app.route("/incoming_call/department", methods=['POST', 'GET'])
def choose_dept():
    resp = VoiceResponse()
    if 'Digits' in request.values:
        # Get which digit the caller chose
        choice = int(request.values['Digits'])
        switcher = {
            1: "es",
            2: "en",
            3: "fr"
        }
        dept_lang = switcher.get(choice)
        resp.redirect("/dept?lang=" + dept_lang + "&digit=" + str(choice))
        return str(resp)


# Select department

@app.route("/dept", methods=['GET', 'POST'])
def dept():
    resp = VoiceResponse()
    dept_lang = request.values['lang']
    digit = request.values['digit']
    say_dict = {
        'es': ["Para ventas oprime uno", "Para apoyo oprime duo", "Para finanzas oprime tres"],
        'en': ["For sales press one", "For support press two", "For billing press three"],
        'fr': [u"Pour ventes pressé un", u"Pour soutien pressé deux", u"Pour finances pressé tres"]
    }
    with resp.gather(num_digits=digit, action="/enqueue_call?lang=" + dept_lang, timeout="10") as g:
        g.say(say_dict.get(dept_lang)[0], language=dept_lang)
        g.say(say_dict.get(dept_lang)[1], language=dept_lang)
        g.say(say_dict.get(dept_lang)[2], language=dept_lang)
    return str(resp)


# Enqueue calls to tasks based on language

@app.route("/enqueue_call", methods=["GET", "POST"])
def enqueue_call():
    if 'Digits' in request.values:
        digit_pressed = request.values['Digits']
        workflow_d = return_work_space(digit_pressed)  # array of workspace and product
        resp = VoiceResponse()
        select_lang = request.values['lang']
        with resp.enqueue(None, workflow_Sid=workflow_d[0]) as e:
            e.task('{"selected_language" : "' + select_lang + '", "selected_product" : "' + workflow_d[1] + '"}')
        return Response(str(resp), mimetype='text/xml')
    else:
        resp = VoiceResponse()
        resp.say("no digits detected")  # tell user something is amiss
        resp.redirect("/incoming_call")  # redirect back to initial step
    return Response(str(resp), mimetype='text/xml')


@app.route('/incoming_call', methods=['POST', 'GET'])
def call():
    resp = VoiceResponse()
    with resp.dial(callerId=caller_id) as r:
        r.client('TomPY')
    return str(resp)


@app.route('/incoming_message', methods=['POST', 'GET'])
def handle_text():
    resp = MessagingResponse()
    # message = Message()
    # message.body('Thanks for contacting ACME Corp, connecting you to a support agent now')
    # resp.append(message)

    chat_users = client.chat.services(chat_service).users.list()
    user_dict = {}

    if len(chat_users) > 0:

        for user in chat_users:

            current_user = client.chat.services(chat_service).users(user.sid).fetch()

            if current_user.identity == request.values['From']:
            # found user
                print('found user')
                current_tasks = client.taskrouter.workspaces(workspace_sid).tasks.list(
                    evaluate_task_attributes='from == "'+ request.values['From']+'"'
                )
                user_channels = client.chat.services(chat_service).users(current_user.sid).user_channels.list()
                print('reached here 1')

                latest_channel = None

                if len(current_tasks) > 0:
                    last_task = current_tasks[-1]
                    if last_task.assignment_status == 'assigned':
                        # check for channel and skip task creation

                        if len(user_channels) > 0:
                            print('user has channel and existing task assigned, updating channel skipping task creation')
                            latest_channel = user_channels[-1].channel_sid
                            sendMessageToChannel(channel=latest_channel, from_=request.values['From'],
                                                 content=request.values['Body'])
                        else:
                           # no current channel create one and then create a new task
                            print('user but no current channel, create channel and task')
                            new_channel = create_channel(user.sid)

                            createSmsTask(from_user=request.values['From'], channel=new_channel.sid,
                                      body=request.values['Body'])
                    elif last_task.assignment_status =='pending':
                        # current task, update channel with latest from the customer
                        print('task is pending')
                        sendMessageToChannel(channel=latest_channel, from_=request.values['From'], content=request.values['Body'])
                    elif last_task.assignment_status == "cancelled":
                        print('task is cancelled')
                    # no current task but user and channel,create new task
                        latest_channel = user_channels[-1].channel_sid
                        createSmsTask(from_user=request.values['From'], channel=latest_channel,
                                  body=request.values['Body'])
                    elif last_task.assignment_status == 'completed':
                        # prior task but it has been completed, create new task
                        latest_channel = user_channels[-1].channel_sid
                        createSmsTask(from_user=request.values['From'], channel=latest_channel,
                              body=request.values['Body'])
                else:
                    # there are no prior tasks - create a new one
                    latest_channel = user_channels[-1].channel_sid
                    createSmsTask(from_user=request.values['From'], channel=latest_channel,
                          body=request.values['Body'])
    else:
        # Brand new user, set up a user, a channel and then create a new task
        print('no user found, creating new user and new task')
        new_user = create_sms_chat_user(request.values['From'])
        new_channel = create_channel(new_user)
        # add the sms body to the channel

        createSmsTask(from_user=request.values['From'], channel=new_channel.sid, body=request.values['Body'])

    return Response(str(resp), mimetype='text/xml')


@app.route('/sendSMS', methods=['GET', 'POST'])
def sendReply():
    if request.values:
        message = client.messages.create(
            from_=caller_id_sms,
            to=request.values['From'],
            body=request.values['Body']
        )
        print(message.sid)

    return Response('200', mimetype='text/json')


###########Agent views ######################

@app.route("/agent_list", methods=['GET', 'POST'])
def generate_agent_list_view():
    # Create arrays of workers and share that with the template so that workers can be queried on the client side

    # get workers with enabled voice-channel
    voice_workers = client.taskrouter.workspaces(workspace_sid) \
        .workers.list(target_workers_expression="worker.channel.voice.configured_capacity > 0")

    # get workers with enabled chat-channel
    chat_workers = client.taskrouter.workspaces(workspace_sid) \
        .workers.list(target_workers_expression="worker.channel.chat.configured_capacity > 0")

    return render_template('agent_list.html', voice_workers=voice_workers, chat_workers=chat_workers)


@app.route("/agents", methods=['GET'])
def generate_view(charset='utf-8'):
    # Agent desktop with Twilio Client
    worker_sid = request.args.get('WorkerSid')  # TaskRouter Worker Token
    worker_capability = WorkerCapabilityToken(
        account_sid=account_sid,
        auth_token=auth_token,
        workspace_sid=workspace_sid,
        worker_sid=worker_sid
    )  # generate worker capability token

    worker_capability.allow_update_activities()  # allow agent to update their activity status e.g. go offline
    worker_capability.allow_update_reservations()  # allow agents to update reservations e.g. accept/reject
    worker_token = worker_capability.to_jwt(ttl=28800)

    capability = ClientCapabilityToken(account_sid, auth_token)  # agent Twilio Client capability token
    capability.allow_client_outgoing(twiml_app)
    capability.allow_client_incoming(worker_sid)

    client_token = capability.to_jwt()

    # render client/worker tokens to the agent desktop so that they can be queried on the client side
    return render_template('agent_desktop.html', token=client_token.decode("utf-8"),
                           worker_token=worker_token.decode("utf-8"),
                           client_=worker_sid, activity=activity,
                           caller_id=caller_id)


@app.route("/agents/noclient", methods=['GET', 'POST'])
def noClientView():
    # Agent desktop without Twilio Client
    worker_sid = request.args.get('WorkerSid')  # TaskRouter Worker Token
    worker_capability = WorkerCapabilityToken(
        account_sid=account_sid,
        auth_token=auth_token,
        workspace_sid=workspace_sid,
        worker_sid=worker_sid
    )  # generate worker capability token

    worker_capability.allow_update_activities()  # allow agent to update their activity status e.g. go offline
    worker_capability.allow_update_reservations()  # allow agents to update reservations e.g. accept/reject

    worker_token = worker_capability.to_jwt(ttl=28800)

    return render_template('agent_desktop_no_client.html.html', worker_token=worker_token.decode(
        "utf-8"))  # render worker token to the agent desktop so that they can be queried on the client side


# Callbacks

@app.route("/conference_callback", methods=['GET', 'POST'])
def conference_callback():
    # monitor for when the customer leaves a conference and output something to the console

    if 'StatusCallbackEvent' in request.values and 'CallSid' in request.values:

        cb_event = request.values.get('StatusCallbackEvent')
        conf_moderator = request.values.get('StartConferenceOnEnter')

        if request.values.get("CallSid"):
            call = client.calls(request.values.get("CallSid")).fetch()
            caller = call.from_

            # send a survey message after the call, but make sure to exclude escallations
            if cb_event == "participant-leave" and caller != caller_id:
                if conf_moderator == "true":
                    message = client.messages.create(
                        to=caller,
                        from_=caller_id,
                        body="Thanks for calling OwlCorp, how satisfied were you with your designated agent on a scale of 1 to 10?")
                else:
                    print("Something else happened: " + cb_event)
        return '', 204

    return render_template('status.html')


@app.route("/recording_callback", methods=['GET', 'POST'])
def recording_callback():
    if request.values.get('RecordingUrl'):
        print('received recording url: ' + request.values.get('RecordingUrl'))
        return '', 204


@app.route("/callTransfer", methods=['GET', 'POST'])
def transferCall():
    # transfer call
    # put the customer call on hold
    participant = client \
        .conferences(request.values.get('conference')) \
        .participants(request.values.get('participant')) \
        .update(hold=True)

    # create new task for the manager escalation
    # add new attributes on the task for customer from number, customer tasksid, selected_language and conference SID

    # todo: manager workflow is set manually for now, scope for making that a variable based on who the worker is selecting to escalate to in the next version   
    task = client.taskrouter.workspaces(workspace_sid).tasks \
        .create(workflow_sid=workflow_mngr, task_channel="voice",
                attributes='{"selected_product":"manager' +
                           '", "selected_language":"' + request.values.get('selected_language') +
                           '", "conference":"' + request.values.get('conference') +
                           '", "customer":"' + request.values.get('participant') +
                           '", "customer_taskSid":"' + request.values.get('taskSid') +
                           '", "from":"' + request.values.get('from') + '"}')

    resp = VoiceResponse
    return Response(str(resp), mimetype='text/xml')


@app.route("/callmute", methods=['GET', 'POST'])
def unmuteCall():
    # put the customer call on hold
    # grab the conferenceSid and customerCallSid from the values sent by the agent UI

    participant = client \
        .conferences(request.values.get('conference')) \
        .participants(request.values.get('participant')) \
        .update(hold=request.values.get('muted'))

    resp = VoiceResponse
    return Response(str(resp), mimetype='text/xml')


@app.route("/transferTwiml", methods=['GET', 'POST'])
def transferToManager():
    # create TwiML that dials manager to customer conference as a participant

    response = VoiceResponse()
    dial = Dial()
    dial.conference(request.values.get('conference'))
    response.append(dial)

    return Response(str(response), mimetype='text/xml')


@app.route('/chat/')
def chat():
    return render_template('chat.html')


@app.route('/createCustomerChannel', methods=['POST, GET'])
def createCustomerChannel():
    channel = request.values.get('taskSid')

    return channel


@app.route('/createChatTask/', methods=['POST', 'GET'])
def createChatTask():
    task = client.taskrouter.workspaces(workspace_sid).tasks \
        .create(workflow_sid=workflow_sid, task_channel="chat",
                attributes='{"selected_product":"chat", "channel":"' + request.values.get("channel") + '"}')
    task_sid = {"TaskSid": task.sid}
    return jsonify(task_sid)


@app.route('/agent_chat')
def agentChat():
    activity = {}
    activities = client.taskrouter.workspaces(workspace_sid).activities.list()
    for a in activities:
        activity[a.friendly_name] = a.sid

    worker_sid = request.args.get('WorkerSid')  # TaskRouter Worker Token
    worker_capability = WorkerCapabilityToken(
        account_sid=account_sid,
        auth_token=auth_token,
        workspace_sid=workspace_sid,
        worker_sid=worker_sid
    )  # generate worker capability token

    worker_capability.allow_update_activities()  # allow agent to update their activity status e.g. go offline
    worker_capability.allow_update_reservations()  # allow agents to update reservations e.g. accept/reject

    worker_token = worker_capability.to_jwt(ttl=28800)  # 8 hours

    return render_template('agent_desktop_chat.html', worker_token=worker_token.decode("utf-8"), activity=activity)


@app.route('/escalateChat/', methods=['POST'])
def escalateChat():
    task = client.taskrouter.workspaces(workspace_sid).tasks \
        .create(workflow_sid=workflow_mngr, task_channel="chat",
                attributes='{"selected_product":"manager", "escalation_type": "chat", "channel":"' + request.values.get(
                    "channel") + '"}')
    print("Escalation to manager created " + task.sid)
    task_sid = {"TaskSid": task.sid}

    return jsonify(task_sid)


# @app.route('/getMessageBody', methods=['GET'])
# def getfirstMessage():
#     channel =request.values['channel']
#     first_message = client.chat.services(chat_service).channels(channel).messages.list()
#     update channel = client.chat.services(chat_service).channels(channel).messages.create(from_=)

@app.route('/postChat/', methods=['GET'])
def returnTranscript(charset='utf-8'):

    messages = []
    get_transcript = client.chat \
        .services(chat_service) \
        .channels(request.values.get("channel")) \
        .messages \
        .list()

    for message in get_transcript:
        messages.append(message.from_ + ": " + message.body)
        print(message.from_ + ": " + message.body)

    data = []

    for messages in get_transcript:
        item = {"message": message.from_ + ": " + message.body}
        data.append(item)

    return render_template('chat_transcript.html', chat_messages=data)


@app.route('/postChat/', methods=['POST'])
def getTranscript():
    # output chat transcript to console
    print(chat_service)
    channel = request.values.get("channel")
    identity = request.values.get("identity")
    messages = []
    # leave channel

    response = client.chat \
        .services(chat_service) \
        .channels(channel) \
        .members(identity) \
        .delete()

    if request.values['type'] == 'chat':
        # update channel to state user has left

        leave_message = client.chat \
            .services(chat_service) \
            .channels(channel) \
            .messages \
            .create(identity + " has left the chat.")

    get_transcript = client.chat \
        .services(chat_service) \
        .channels(channel) \
        .messages \
        .list()

    # delete channel

    # response = client.chat \
    #     .services(chat_service) \
    #     .channels(request.values.get("channel")) \
    #     .delete()

    for message in get_transcript:
        messages.append(message.from_ + ": " + message.body)
        print(message.from_ + ": " + message.body)

    return render_template('chat_transcript.html')


# Basic health check - check environment variables have been configured
# correctly
@app.route('/config')
def config():
    return jsonify(
        account_sid,
        api_key,
        api_secret,
        chat_service,
    )


@app.route('/token', methods=['GET'])
def randomToken():
    username = request.values.get("identity")
    return generateToken(username)


@app.route('/synctoken', methods=['GET'])
def randomsyncToken():
    username = request.values.get("identity")
    return generateSyncToken(username)


@app.route('/token', methods=['POST'])
def createToken(username):
    # Get the request json or form data
    content = request.get_json() or request.form
    # get the identity from the request, or make one up
    identity = content.get('identity', username)
    return generateToken(identity)


@app.route('/synctoken', methods=['POST'])
def createsyncToken(username):
    # Get the request json or form data
    content = request.get_json() or request.form
    # get the identity from the request, or make one up
    identity = content.get('identity', username)
    return generateSyncToken(identity)


@app.route('/token/<identity>', methods=['POST', 'GET'])
def token(identity):
    return generateToken(identity)


@app.route('/synctoken/<identity>', methods=['POST', 'GET'])
def synctoken(identity):
    return generateSyncToken(identity)


@app.route('/syncStatus', methods=['GET', 'POST'])
def returnStatus():
    status = ''

    return status


def generateToken(identity):
    # Create access token with credentials
    token = AccessToken(account_sid, api_key, api_secret, identity=identity)

    if chat_service:
        chat_grant = ChatGrant(service_sid=chat_service)
        token.add_grant(chat_grant)

    # Return token info as JSON
    return jsonify(identity=identity, token=token.to_jwt().decode('utf-8'))


def generateSyncToken(identity):
    # Create access token with credentials
    token = AccessToken(account_sid, api_key, api_secret, identity=identity)

    if sync_service:
        sync_grant = SyncGrant(service_sid=sync_service)

        token.add_grant(sync_grant)
    # Return token info as JSON
    return jsonify(identity=identity, token=token.to_jwt().decode('utf-8'))


if __name__ == "__main__":
    app.run(debug=True)
