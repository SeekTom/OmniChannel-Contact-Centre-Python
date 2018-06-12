from twilio.rest import Client
import os

# Your Account Sid and Auth Token from twilio.com/user/account
account = os.environ.get("TWILIO_ACME_ACCOUNT_SID")
token = os.environ.get("TWILIO_ACME_AUTH_TOKEN")
chat_service = os.environ.get("TWILIO_ACME_CHAT_SERVICE_SID")

client = Client(account, token)

members = client.chat \
               .services(chat_service) \
               .users.list()

for member in members:
    print(member.sid, member.identity)
    delete = input('Delete user?')
    if delete == 'y':
        delete = client.chat.services(chat_service).users(member.sid).delete()


