import pytz
JOIN_QUEUE_PAYLOAD = "join_queue_"
JOIN_GROUP_PAYLOAD = "join_group_"
GMT_PLUS_5 = pytz.timezone("Etc/GMT-5")
MAX_DISTANCE = 150

# States для ConversationHandler (create_queue)
QUEUE_NAME, QUEUE_DATE, QUEUE_TIME, CHOOSE_LOCATION, CHOOSE_GROUP, SEND_NOTIFICATION, TIME_WITHOUT_LOCATION = range(7)
# States для ConversationHandler (change_name)
CHANGE_NAME = 0
# States для ConversationHandler (broadcast)
BROADCAST_MESSAGE, BROADCAST_RECIPIENTS , BROADCAST_SCHEDULE = range(3)
DELETE_BROADCAST = 0

GROUP_NAME = 0
WAITING_FOR_NAME = 0
SELECT_TIMEZONE, SELECT_TIMEZONE_BY_LOCATION = range(2)

RUSSIAN_TIMEZONES = {
    "Калининград (GMT+2)": "Europe/Kaliningrad",
    "Москва (GMT+3)": "Europe/Moscow",
    "Самара (GMT+4)": "Europe/Samara",
    "Екатеринбург (GMT+5)": "Asia/Yekaterinburg",
    "Омск (GMT+6)": "Asia/Omsk",
    "Красноярск (GMT+7)": "Asia/Krasnoyarsk",
    "Иркутск (GMT+8)": "Asia/Irkutsk",
    "Якутск (GMT+9)": "Asia/Yakutsk",
    "Владивосток (GMT+10)": "Asia/Vladivostok",
    "Магадан (GMT+11)": "Asia/Magadan",
    "Камчатка (GMT+12)": "Asia/Kamchatka"
}