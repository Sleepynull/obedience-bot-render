# Obedience Discord Bot - Render Deployment

A Discord bot for BDSM-themed habit tracking with tasks, rewards, punishments, and points.

## Features

- **Roles**: Dominant and submissive user types
- **Tasks**: Create daily/weekly tasks with point rewards
- **Points System**: Earn points by completing tasks
- **Rewards & Punishments**: Create and assign to submissives
- **Real-time Notifications**: DM alerts for completions and assignments
- **Statistics**: View completion graphs and progress

## Deploy to Render (Free 24/7 Hosting)

### Step 1: Get Your Discord Bot Token

1. Go to https://discord.com/developers/applications
2. Create a "New Application" → Give it a name
3. Go to the "Bot" tab → Click "Add Bot"
4. **Enable these Intents** (under "Privileged Gateway Intents"):
   - ✅ Server Members Intent
   - ✅ Message Content Intent
5. Click "Reset Token" → Copy the token (you'll need this later)
6. Go to "OAuth2" → "URL Generator":
   - Scopes: Select `bot` and `applications.commands`
   - Bot Permissions: Select "Administrator" (or minimum: Send Messages, Embed Links, Attach Files, Use Slash Commands)
7. Copy the generated URL and open it to invite the bot to your Discord server

### Step 2: Deploy to Render

1. **Sign up for Render**
   - Go to https://render.com
   - Click "Get Started for Free"
   - Sign up with your GitHub account

2. **Connect This Repository to GitHub**
   - Push this code to a new GitHub repository (public or private)
   - Or fork/copy this repository to your GitHub account

3. **Create a Background Worker on Render**
   - In Render dashboard, click "New +" → "Background Worker"
   - Connect your GitHub repository
   - Configure:
     - **Name**: `obedience-bot` (or any name you prefer)
     - **Environment**: `Python 3`
     - **Build Command**: `pip install -r requirements.txt`
     - **Start Command**: `python bot.py`
     - **Instance Type**: `Free`

4. **Add Environment Variable**
   - Scroll to "Environment Variables" section
   - Click "Add Environment Variable"
   - **Key**: `DISCORD_TOKEN`
   - **Value**: Paste your Discord bot token from Step 1
   - Click "Save"

5. **Deploy**
   - Click "Create Background Worker"
   - Render will build and deploy your bot automatically
   - Check the "Logs" tab - you should see:
     ```
     Synced 15 command(s)
     <BotName>#1234 is now online!
     ```

🎉 **Your bot is now running 24/7!**

## Using the Bot

### Getting Started

1. In your Discord server, type `/register`
   - Dominant users select "Dominant"
   - Submissive users select "Submissive"

2. Link a relationship: `/link submissive:@username`

3. View all commands: `/help`

### Key Commands

**For Dominants:**
- `/task_add` - Create a task for a submissive
- `/reward_create` - Create a reward
- `/punishment_create` - Create a punishment
- `/reward_assign` - Give a reward
- `/punishment_assign` - Give a punishment

**For Submissives:**
- `/tasks` - View your tasks
- `/task_complete` - Mark a task as done
- `/points` - Check your points
- `/stats` - View your completion statistics

**For Everyone:**
- `/rewards` - View available rewards
- `/punishments` - View available punishments
- `/help` - Show all commands

## Important Notes

### Database Persistence
⚠️ **Render's free tier has ephemeral storage** - your database will reset when the service restarts or redeploys.

**Options:**
- **Upgrade to Render's Starter plan ($7/month)** - includes persistent disk storage
- **Use an external database** - Connect PostgreSQL from Railway, Supabase, or PlanetScale (free tiers available)
- **Accept data loss** - Fine for testing or casual use where occasional resets are acceptable

### Updating the Bot
Every time you push code changes to GitHub, Render will automatically redeploy your bot.

### Viewing Logs
- Go to your Render dashboard
- Click on your background worker
- View the "Logs" tab for real-time output

## Troubleshooting

**Bot not starting?**
- Check Render logs for errors
- Verify `DISCORD_TOKEN` environment variable is set correctly
- Ensure Discord intents are enabled in Developer Portal

**Bot not responding to commands?**
- Make sure you invited the bot to your server with correct permissions
- Check that commands have synced (see "Synced X command(s)" in logs)
- Try waiting a few minutes for Discord to propagate slash commands

**Database resets frequently?**
- This is normal on Render's free tier
- Consider upgrading to paid plan or using external database

## Support

For issues or questions, check the bot logs on Render or review your Discord Developer Portal settings.

## Tech Stack

- Python 3.11
- discord.py
- SQLite (ephemeral on free tier)
- matplotlib (for stats graphs)
