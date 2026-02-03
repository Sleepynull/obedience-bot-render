# Configuration for the Obedience Bot

# Server Mode Configuration
# Set to "whitelist" to restrict bot to specific servers
# Set to "global" to allow bot to work in all servers
SERVER_MODE = "global"  # Options: "whitelist" or "global"

# Whitelist of allowed server IDs (only used when SERVER_MODE = "whitelist")
# Add your Discord server IDs here
# Example: ALLOWED_SERVERS = [123456789012345678, 987654321098765432]
ALLOWED_SERVERS = [
    # Add your server IDs here, one per line
    # You can find server ID by right-clicking server name with Developer Mode enabled
]

# If True, bot will respond to commands in DMs (direct messages)
# If False, bot will ignore all DM commands
ALLOW_DMS = False

# Channel Notifications Configuration
# Set channel names where the bot should post notifications
# Set to None to disable notifications for that type
# Bot will search for these channel names in the server where the command is used
TASK_CHANNEL_NAME = "task"  # Channel name for new task assignments
PUNISHMENT_CHANNEL_NAME = "punishment"  # Channel name for punishment assignments
REWARD_CHANNEL_NAME = "reward"  # Channel name for reward redemptions
APPROVAL_CHANNEL_NAME = "approve-or-reject"  # Channel name for approval/rejection notifications
