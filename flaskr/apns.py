import asyncio
from aioapns import APNs, NotificationRequest, PushType


def _instanciate_client():
    return APNs(
        key='APNPush+AuthKey_8DCDJT2U7Q.p8',
        key_id='8DCDJT2U7Q',
        team_id='65874G65QX',
        topic='pass.membership.lebarp',  # Bundle ID
        use_sandbox=False,
    )

apns_key_client = _instanciate_client()

async def notify(pushToken: str):
    request = NotificationRequest(
        device_token=pushToken,
        message = {
            "aps": {
                "alert": "Hello from APNs",
                "badge": "1"
            }
        },
    )
    print(f'Notification: sending for token {pushToken}')
    a = await apns_key_client.send_notification(request)
    print(f'Notification: {a} - {a.is_successful} {a.status} {a.notification_id} {a.status}')
    return a.status
