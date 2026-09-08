from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build

SCOPES = [
    "https://www.googleapis.com/auth/gmail.readonly",
    "https://www.googleapis.com/auth/gmail.compose",
]

flow = InstalledAppFlow.from_client_secrets_file("tools/credentials.json", SCOPES)
creds = flow.run_local_server(port=0)

with open("tools/token.json", "w") as f:
    f.write(creds.to_json())

service = build("gmail", "v1", credentials=creds)
print(service.users().getProfile(userId="me").execute()["emailAddress"])