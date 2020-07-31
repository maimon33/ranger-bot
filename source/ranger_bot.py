import ranger as Ranger

class RangerReport:
    """Constructs the onboarding message and stores the state of which tasks were completed."""

    WELCOME_BLOCK = {
        "type": "section",
        "text": {
            "type": "mrkdwn",
            "text": (
                "You triggered Ranger...\n\n"
                "*Waiting for assets*"
            ),
        },
    }
    DIVIDER_BLOCK = {"type": "divider"}

    def __init__(self, channel):
        self.channel = channel
        self.username = "pythonboardingbot"
        self.icon_emoji = ":robot_face:"
        self.timestamp = ""

    def get_message_payload(self):
        return {
            "ts": self.timestamp,
            "channel": self.channel,
            "username": self.username,
            "icon_emoji": self.icon_emoji,
            "blocks": [
                self.WELCOME_BLOCK,
                self.DIVIDER_BLOCK,
                *self._run_ranger(),
            ],
        }

    def _run_ranger(self):
        return {
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": Ranger.ranger(init=True, region="eu-west-1", table=True, execute=False),
            },
        }
