# Obedience Discord Bot - Render Deployment

A Discord bot for BDSM-themed habit tracking with tasks, rewards, punishments, and points.

## Features

- **Roles**: Dominant and submissive user types with automatic Discord role assignment
- **Tasks**: Create daily/weekly/custom recurring tasks with point rewards and optional deadlines
- **Advanced Scheduling**: Tasks can repeat on specific days/times (e.g., Mon/Wed/Fri at 6:00 AM)
- **Points System**: Earn points by completing tasks, lose points for missed deadlines
- **Rewards & Punishments**: Create templates and assign to submissives
- **Auto-Punishments**: Link punishments to tasks or point thresholds for automatic assignment
- **Random Punishments**: Assign random punishment from your pool
- **Image Proof Required**: Submissives must attach photos for task/punishment completion
- **Approval System**: Dominants review and approve/reject submissions
- **Deadline Tracking**: Auto-deduct points for missed deadlines, double penalties for late punishments
- **Point Refunds**: Late submissions refund penalties when approved
- **Real-time Notifications**: DM alerts for completions, assignments, and deadline misses
- **Statistics**: View completion graphs and progress
- **Management Tools**: Delete tasks/rewards/punishments/thresholds as needed

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
     Synced 31 command(s)
     <BotName>#1234 is now online!
     ```

🎉 **Your bot is now running 24/7!**

## Using the Bot

### Getting Started

1. In your Discord server, type `/register`
   - Dominant users select "Dominant"
   - Submissive users select "Submissive"
   - The bot will automatically assign you a "Dominant" or "Submissive" Discord role if it exists in your server

2. Link a relationship: `/link submissive:@username`

3. View all commands: `/help`

### All Commands (31 Total)

#### Registration & Setup
- `/register role:<Dominant|Submissive>` - Register with the bot
- `/link submissive:@user` - Link dominant with submissive

#### Task Management (Dominant Only)
- `/task_add submissive:@user title:"..." description:"..." frequency:<daily|weekly|custom> [points] [deadline_hours] [recurring] [days_of_week] [time_of_day] [interval_hours]` - Create a task
  - Example: `frequency:Weekly recurring:True days_of_week:"Mon,Wed,Fri" time_of_day:"06:00"` for recurring Mon/Wed/Fri at 6 AM
- `/tasks [submissive:@user]` - View tasks (dominant views submissive's, submissive views own)
- `/task_delete task_id:<id>` - Delete a task permanently
- `/task_link_punishment task_id:<id> punishment_id:<id>` - Auto-assign punishment when task deadline is missed

#### Task Completion (Submissive Only)
- `/task_complete task_id:<id> proof:<image>` - Submit task completion with image proof

#### Rewards (Dominant Creates, Submissives View)
- `/reward_create title:"..." description:"..." [cost]` - Create reward template (dominant)
- `/rewards` - View available rewards
- `/reward_assign submissive:@user reward_id:<id> [reason]` - Assign reward to submissive (dominant)
- `/reward_delete reward_id:<id>` - Delete reward template (dominant)

#### Punishments (Dominant Creates, Submissives View)
- `/punishment_create title:"..." description:"..."` - Create punishment template (dominant)
- `/punishments` - View available punishments
- `/punishment_assign submissive:@user punishment_id:<id> [reason] [deadline_hours] [point_penalty]` - Assign punishment (dominant)
- `/punishment_assign_random submissive:@user [reason] [deadline_hours] [point_penalty]` - Assign random punishment (dominant)
- `/punishment_delete punishment_id:<id>` - Delete punishment template (dominant)
- `/punishments_active` - View your active punishments (submissive)

#### Punishment Completion (Submissive Only)
- `/punishment_complete assignment_id:<id> proof:<image>` - Submit punishment proof

#### Auto-Punishment System (Dominant Only)
- `/threshold_create threshold_points:<points> punishment_id:<id> [submissive:@user]` - Auto-assign punishment when points drop below threshold
- `/thresholds` - View all your point thresholds
- `/threshold_delete threshold_id:<id>` - Delete a point threshold

#### Approval & Review (Dominant Only)
- `/approve completion_id:<id>` - Approve task completion
- `/reject completion_id:<id> [reason]` - Reject task completion
- `/punishment_approve assignment_id:<id>` - Approve punishment completion
- `/punishment_reject assignment_id:<id> [reason]` - Reject punishment (submissive must resubmit)
- `/punishment_cancel assignment_id:<id> [reason]` - Cancel punishment (no resubmission required)
- `/pending` - View all pending task completions
- `/verify` - View pending punishment completions

#### Points & Stats
- `/points` - Check your points and affordable rewards
- `/stats [days]` - View completion statistics with graphs

#### Help
- `/help` - Show all available commands

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
