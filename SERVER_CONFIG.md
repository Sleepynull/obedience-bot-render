# Server Configuration Guide

This bot supports two modes: **Global** and **Whitelist**.

## Configuration File

Edit `config.py` to configure server access settings.

## Modes

### Global Mode (Default for Public Bots)
```python
SERVER_MODE = "global"
```
- Bot responds to commands in **all servers** where it's invited
- Data is shared across all servers
- Use this if you want one unified obedience tracking system across multiple servers

### Whitelist Mode (Recommended for Private Use)
```python
SERVER_MODE = "whitelist"
ALLOWED_SERVERS = [
    123456789012345678,  # Your server ID here
    987654321098765432,  # Another server ID
]
```
- Bot **only** responds in servers listed in `ALLOWED_SERVERS`
- Prevents unauthorized use if bot token leaks
- Recommended for private/personal bot deployments

## Getting Your Server ID

1. Enable Developer Mode in Discord:
   - Settings → App Settings → Advanced → Developer Mode
2. Right-click your server name
3. Click "Copy Server ID"
4. Paste the ID into `ALLOWED_SERVERS` list in `config.py`

## DM (Direct Message) Settings

```python
ALLOW_DMS = False  # Set to True to allow commands via DMs
```

- `False`: Bot ignores all commands sent via DMs
- `True`: Bot responds to commands in DMs (data remains global)

## Example Configurations

### Single Private Server
```python
SERVER_MODE = "whitelist"
ALLOWED_SERVERS = [123456789012345678]
ALLOW_DMS = False
```

### Multiple Servers (Shared Data)
```python
SERVER_MODE = "global"
ALLOWED_SERVERS = []  # Not used in global mode
ALLOW_DMS = True
```

### Development/Testing
```python
SERVER_MODE = "whitelist"
ALLOWED_SERVERS = [
    123456789012345678,  # Production server
    111111111111111111,  # Test server
]
ALLOW_DMS = True  # Allow testing via DMs
```

## Important Notes

⚠️ **Data is always global** - All registered users, tasks, and relationships are shared across all allowed servers. This configuration only controls WHERE the bot responds, not WHERE data is stored.

🔒 **Whitelist mode is highly recommended** for personal/private bots to prevent unauthorized access.

## After Changing Configuration

1. Save `config.py`
2. Restart the bot (or redeploy on Render)
3. Check bot logs for confirmation:
   - Whitelist mode: `Server whitelist mode: X server(s) allowed`
   - Global mode: `Global mode: Bot will work in all servers`
