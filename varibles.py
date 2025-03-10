import pytz
JOIN_QUEUE_PAYLOAD = "join_"
JOIN_GROUP_PAYLOAD = "join_group_"
GMT_PLUS_5 = pytz.timezone("Etc/GMT+5")
MAX_DISTANCE = 250

# States для ConversationHandler (create_queue)
QUEUE_NAME, QUEUE_DATE, QUEUE_TIME, CHOOSE_LOCATION, CHOOSE_GROUP, SEND_NOTIFICATION = range(6)
# States для ConversationHandler (change_name)
CHANGE_NAME = 0
# States для ConversationHandler (broadcast)
BROADCAST_MESSAGE, BROADCAST_RECIPIENTS , BROADCAST_SCHEDULE = range(3)
DELETE_BROADCAST = 0

GROUP_NAME = 0

WAITING_FOR_NAME = "waiting_for_name"
