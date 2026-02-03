import discord
from discord.ext import commands, tasks
from discord import app_commands
import os
from dotenv import load_dotenv
import database as db
import io
import matplotlib
import datetime
import pytz
import config  # Import server configuration
matplotlib.use('Agg')  # Non-GUI backend
import matplotlib.pyplot as plt

# Load environment variables
load_dotenv()
TOKEN = os.getenv('DISCORD_TOKEN')

# Bot setup
intents = discord.Intents.default()
intents.message_content = True
intents.members = True

bot = commands.Bot(command_prefix='!', intents=intents)

# Server access check function
def is_server_allowed(guild_id: int = None) -> bool:
    """Check if command can be executed in this server/DM."""
    # Handle DMs
    if guild_id is None:
        return config.ALLOW_DMS
    
    # Handle server whitelist
    if config.SERVER_MODE == "whitelist":
        return guild_id in config.ALLOWED_SERVERS
    
    # Global mode - all servers allowed
    return True

# Global interaction check for all commands
@bot.tree.interaction_check
async def interaction_check(interaction: discord.Interaction) -> bool:
    """Check if interaction is allowed before processing any command."""
    guild_id = interaction.guild_id if interaction.guild else None
    if not is_server_allowed(guild_id):
        await interaction.response.send_message(
            "❌ This bot is not configured to work in this server or in DMs.\nContact the bot owner if you believe this is a mistake.",
            ephemeral=True
        )
        return False
    return True

# Helper function to post notifications to designated channels
async def post_to_channel(guild: discord.Guild, channel_name: str, embed: discord.Embed) -> bool:
    """Post an embed to a designated notification channel."""
    if not channel_name or not guild:
        print(f"[CHANNEL] Skipped: channel_name={channel_name}, guild={guild}")
        return False
    
    # Search for channel by name (case-insensitive)
    channel = discord.utils.get(guild.text_channels, name=channel_name.lower())
    
    if channel:
        try:
            await channel.send(embed=embed)
            print(f"[CHANNEL] Posted to #{channel_name} in {guild.name}")
            return True
        except discord.Forbidden:
            print(f"[CHANNEL] Missing permissions to post in #{channel_name}")
        except Exception as e:
            print(f"[CHANNEL] Error posting to #{channel_name}: {e}")
    else:
        print(f"[CHANNEL] Channel '#{channel_name}' not found in {guild.name}. Available channels: {[c.name for c in guild.text_channels]}")
    
    return False

@tasks.loop(minutes=5)
async def check_deadlines():
    """Check for expired tasks and punishments, deduct points."""
    # Check expired tasks
    expired_tasks = await db.get_expired_tasks()
    
    for task in expired_tasks:
        # Deduct points
        points_to_deduct = task['point_value']
        new_total = await db.update_points(task['submissive_id'], -points_to_deduct)
        
        # Check if task has linked punishment and auto-assign it
        punishment_id = task.get('auto_punishment_id')
        punishment_assigned = False
        assignment_id = None
        punishment_title = None
        if punishment_id:
            # If punishment_id is -1, assign a random punishment
            if punishment_id == -1:
                random_punishment = await db.get_random_punishment(task['dominant_id'])
                if random_punishment:
                    punishment_id = random_punishment['id']
                    punishment_title = random_punishment['title']
                else:
                    punishment_id = None  # No punishments available
            
            if punishment_id and punishment_id != -1:
                deadline = datetime.datetime.now() + datetime.timedelta(hours=24)
                assignment_id = await db.assign_punishment(
                    task['submissive_id'], 
                    task['dominant_id'], 
                    punishment_id, 
                    f"Auto-assigned for missing task: {task['title']}", 
                    deadline, 
                    10
                )
                punishment_assigned = True
        
        # Check point thresholds
        thresholds = await db.check_point_thresholds(task['submissive_id'], new_total)
        for threshold in thresholds:
            deadline = datetime.datetime.now() + datetime.timedelta(hours=24)
            await db.assign_punishment(
                task['submissive_id'],
                threshold['dominant_id'],
                threshold['punishment_id'],
                f"Auto-assigned for dropping below {threshold['threshold_points']} points",
                deadline,
                10
            )
            await db.mark_threshold_triggered(threshold['id'])
        
        # Deactivate task
        await db.deactivate_expired_task(task['id'])
        
        # Notify submissive
        try:
            sub_user = await bot.fetch_user(task['submissive_id'])
            embed = discord.Embed(
                title="⏰ Task Deadline Missed",
                description=f"You missed the deadline for: **{task['title']}**",
                color=discord.Color.red()
            )
            embed.add_field(name="Points Deducted", value=str(points_to_deduct), inline=True)
            embed.add_field(name="New Total", value=str(new_total), inline=True)
            if punishment_assigned:
                punish_text = f"Assignment ID: {assignment_id}\nDeadline: 24 hours"
                if punishment_title:
                    punish_text = f"**{punishment_title}**\n" + punish_text
                embed.add_field(name="⚠️ Punishment Auto-Assigned", value=punish_text, inline=False)
            await sub_user.send(embed=embed)
        except:
            pass
        
        # Notify dominant
        try:
            dom_user = await bot.fetch_user(task['dominant_id'])
            embed = discord.Embed(
                title="⏰ Task Deadline Expired",
                description=f"Task **{task['title']}** expired without completion.",
                color=discord.Color.orange()
            )
            embed.add_field(name="Submissive ID", value=str(task['submissive_id']), inline=True)
            embed.add_field(name="Points Deducted", value=str(points_to_deduct), inline=True)
            if punishment_assigned:
                embed.add_field(name="Punishment Auto-Assigned", value=f"Assignment ID: {assignment_id}", inline=True)
            await dom_user.send(embed=embed)
        except:
            pass
    
    # Check expired punishments
    expired_punishments = await db.get_expired_punishments()
    
    for punishment in expired_punishments:
        # Double the penalty and deduct points
        penalty = punishment['point_penalty']
        doubled_penalty = penalty * 2
        new_total = await db.update_points(punishment['submissive_id'], -doubled_penalty)
        
        # Mark as expired and double penalty
        await db.expire_punishment(punishment['id'], double_penalty=True)
        
        # Notify submissive
        try:
            sub_user = await bot.fetch_user(punishment['submissive_id'])
            embed = discord.Embed(
                title="⏰ Punishment Deadline Missed",
                description=f"You missed the deadline for punishment assignment #{punishment['id']}",
                color=discord.Color.dark_red()
            )
            embed.add_field(name="Penalty Doubled", value=f"-{doubled_penalty} points (was -{penalty})", inline=True)
            embed.add_field(name="New Total", value=str(new_total), inline=True)
            embed.set_footer(text="You can still submit proof - approval will refund the penalty")
            await sub_user.send(embed=embed)
        except:
            pass
        
        # Notify dominant
        try:
            dom_user = await bot.fetch_user(punishment['dominant_id'])
            embed = discord.Embed(
                title="⏰ Punishment Deadline Expired",
                description=f"Punishment assignment #{punishment['id']} expired without proof.",
                color=discord.Color.orange()
            )
            embed.add_field(name="Submissive ID", value=str(punishment['submissive_id']), inline=True)
            embed.add_field(name="Penalty Doubled", value=f"-{doubled_penalty} points", inline=True)
            await dom_user.send(embed=embed)
        except:
            pass

@tasks.loop(minutes=5)
async def check_recurring_tasks():
    """Check for completed recurring tasks that need to be reset."""
    tasks_to_reset = await db.get_tasks_to_reset()
    
    for task in tasks_to_reset:
        await db.reset_recurring_task(task['id'])
        
        # Notify submissive about reset task
        try:
            sub_user = await bot.fetch_user(task['submissive_id'])
            embed = discord.Embed(
                title="🔄 Task Reset",
                description=f"Your recurring task **{task['title']}** has been reset and is ready again!",
                color=discord.Color.blue()
            )
            embed.add_field(name="Frequency", value=task['frequency'].capitalize(), inline=True)
            embed.add_field(name="Points", value=str(task['point_value']), inline=True)
            
            # Show next occurrence if available
            next_occur = task.get('next_occurrence')
            if next_occur:
                next_dt = datetime.datetime.fromisoformat(next_occur)
                embed.add_field(name="Available Until", value=f"<t:{int(next_dt.timestamp())}:R>", inline=False)
            
            await sub_user.send(embed=embed)
        except:
            pass

@bot.event
async def on_ready():
    """Initialize bot when ready."""
    await db.init_db()
    check_deadlines.start()  # Start deadline checker
    check_recurring_tasks.start()  # Start recurring task reset checker
    try:
        synced = await bot.tree.sync()
        print(f"Synced {len(synced)} command(s)")
    except Exception as e:
        print(f"Failed to sync commands: {e}")
    print(f'{bot.user} is now online!')
    
    # Print server configuration status
    if config.SERVER_MODE == "whitelist":
        if config.ALLOWED_SERVERS:
            print(f"Server whitelist mode: {len(config.ALLOWED_SERVERS)} server(s) allowed")
        else:
            print("⚠️ WARNING: Server whitelist mode is enabled but no servers are configured!")
    else:
        print("Global mode: Bot will work in all servers")

@bot.tree.error
async def on_app_command_error(interaction: discord.Interaction, error: app_commands.AppCommandError):
    """Global error handler for app commands."""
    # Check if error is due to server restriction
    guild_id = interaction.guild_id if interaction.guild else None
    if not is_server_allowed(guild_id):
        try:
            await interaction.response.send_message(
                "❌ This bot is not configured to work in this server or in DMs.",
                ephemeral=True
            )
        except:
            pass
        return
    
    # Handle other errors
    if isinstance(error, app_commands.CommandOnCooldown):
        await interaction.response.send_message(
            f"⏱️ This command is on cooldown. Try again in {error.retry_after:.1f}s",
            ephemeral=True
        )
    elif isinstance(error, app_commands.MissingPermissions):
        await interaction.response.send_message(
            "❌ You don't have permission to use this command.",
            ephemeral=True
        )
    else:
        # Log other errors
        print(f"Command error: {error}")

# ============ REGISTRATION COMMANDS ============

@bot.tree.command(name="register", description="Register as a dominant or submissive")
@app_commands.describe(role="Your role: dominant or submissive")
@app_commands.choices(role=[
    app_commands.Choice(name="Dominant", value="dominant"),
    app_commands.Choice(name="Submissive", value="submissive")
])
async def register(interaction: discord.Interaction, role: app_commands.Choice[str]):
    """Register a user with their role."""
    # Defer response to prevent timeout
    await interaction.response.defer(ephemeral=True)
    
    success = await db.register_user(interaction.user.id, str(interaction.user), role.value)
    if success:
        # Try to assign Discord role
        role_assigned = False
        if interaction.guild:  # Only works if command is used in a server
            try:
                # Look for a role named "Dominant" or "Submissive" (case-insensitive)
                discord_role = discord.utils.get(
                    interaction.guild.roles,
                    name=role.value.capitalize()
                )
                
                # Only assign if role exists and user doesn't already have it
                if discord_role and discord_role not in interaction.user.roles:
                    await interaction.user.add_roles(discord_role)
                    role_assigned = True
                elif discord_role:
                    # User already has the role
                    role_assigned = True
            except discord.Forbidden:
                pass  # Bot doesn't have permission to manage roles
            except Exception:
                pass  # Other error, just continue
        
        response = f"✅ You've been registered as a **{role.value}**!"
        if role_assigned:
            response += f"\n🏷️ Discord role assigned!"
        elif interaction.guild and not role_assigned:
            response += f"\n⚠️ Note: Create a '{role.value.capitalize()}' role in server settings for automatic role assignment."
        
        await interaction.followup.send(response, ephemeral=True)
    else:
        await interaction.followup.send(
            "❌ You're already registered!",
            ephemeral=True
        )

@bot.tree.command(name="link", description="Link a dominant with a submissive")
@app_commands.describe(submissive="The submissive user to link")
async def link(interaction: discord.Interaction, submissive: discord.Member):
    """Create a relationship between dominant and submissive."""
    # Verify dominant role
    user = await db.get_user(interaction.user.id)
    if not user or user['role'] != 'dominant':
        await interaction.response.send_message(
            "❌ Only dominants can link with submissives!",
            ephemeral=True
        )
        return
    
    # Verify submissive role
    sub_user = await db.get_user(submissive.id)
    if not sub_user or sub_user['role'] != 'submissive':
        await interaction.response.send_message(
            f"❌ {submissive.mention} is not registered as a submissive!",
            ephemeral=True
        )
        return
    
    # Create relationship
    success = await db.create_relationship(interaction.user.id, submissive.id)
    if success:
        await interaction.response.send_message(
            f"✅ Successfully linked with {submissive.mention}!",
            ephemeral=False
        )
    else:
        await interaction.response.send_message(
            "❌ This relationship already exists!",
            ephemeral=True
        )

# ============ TASK COMMANDS ============

@bot.tree.command(name="task_add", description="Add a new task for a submissive")
@app_commands.describe(
    submissive="The submissive to assign the task to",
    title="Task title",
    description="Task description",
    frequency="How often the task recurs",
    points="Points earned on completion (default: 10)",
    deadline_hours="Hours until deadline (optional, e.g., 24 for 1 day)",
    deadline_datetime="Specific deadline (YYYY-MM-DD HH:MM format, e.g., 2026-02-05 15:30)",
    deadline_time="Daily deadline time only (HH:MM format, e.g., 09:00 for 9 AM daily)",
    auto_punish="Assign random punishment if deadline missed (default: False)",
    recurring="Enable auto-reset after completion",
    days_of_week="Days for weekly tasks: Mon,Wed,Fri (use Mon/Tue/Wed/Thu/Fri/Sat/Sun)",
    time_of_day="Time in HH:MM format (24hr, e.g., 14:30 for 2:30 PM)",
    interval_hours="For custom: hours between occurrences"
)
@app_commands.choices(frequency=[
    app_commands.Choice(name="Daily", value="daily"),
    app_commands.Choice(name="Weekly", value="weekly"),
    app_commands.Choice(name="Custom Interval", value="custom")
])
async def task_add(
    interaction: discord.Interaction,
    submissive: discord.Member,
    title: str,
    description: str,
    frequency: app_commands.Choice[str],
    points: int = 10,
    deadline_hours: int = None,
    deadline_datetime: str = None,
    deadline_time: str = None,
    auto_punish: bool = False,
    recurring: bool = False,
    days_of_week: str = None,
    time_of_day: str = None,
    interval_hours: int = None
):
    """Add a new task (dominant only)."""
    # Verify dominant
    user = await db.get_user(interaction.user.id)
    if not user or user['role'] != 'dominant':
        await interaction.response.send_message(
            "❌ Only dominants can create tasks!",
            ephemeral=True
        )
        return
    
    # Verify relationship
    submissives = await db.get_submissives(interaction.user.id)
    if not any(s['user_id'] == submissive.id for s in submissives):
        await interaction.response.send_message(
            f"❌ {submissive.mention} is not linked to you!",
            ephemeral=True
        )
        return
    
    # Process days of week if provided
    days_of_week_str = None
    if days_of_week and frequency.value == 'weekly':
        # Convert day names to weekday numbers
        day_map = {'mon': 0, 'tue': 1, 'wed': 2, 'thu': 3, 'fri': 4, 'sat': 5, 'sun': 6}
        day_list = [d.strip().lower()[:3] for d in days_of_week.split(',')]
        day_numbers = [str(day_map[d]) for d in day_list if d in day_map]
        if day_numbers:
            days_of_week_str = ','.join(day_numbers)
    
    # Get submissive's timezone
    sub_timezone = await db.get_user_timezone(submissive.id)
    user_tz = pytz.timezone(sub_timezone)
    
    # Calculate deadline - prioritize specific datetime > time-only > hours
    deadline = None
    if deadline_datetime:
        try:
            # Parse datetime and localize to user's timezone
            naive_dt = datetime.datetime.strptime(deadline_datetime, "%Y-%m-%d %H:%M")
            deadline = user_tz.localize(naive_dt)
        except ValueError:
            await interaction.response.send_message(
                f"❌ Invalid datetime format! Use: YYYY-MM-DD HH:MM (e.g., 2026-02-05 15:30)\nYour timezone: {sub_timezone}",
                ephemeral=True
            )
            return
    elif deadline_time:
        # Parse time and calculate next occurrence of that time in user's timezone
        try:
            time_parts = deadline_time.split(':')
            hour = int(time_parts[0])
            minute = int(time_parts[1])
            
            # Get current time in user's timezone
            now = datetime.datetime.now(user_tz)
            deadline = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
            
            # If time has already passed today, set for tomorrow
            if deadline <= now:
                deadline = deadline + datetime.timedelta(days=1)
        except (ValueError, IndexError):
            await interaction.response.send_message(
                f"❌ Invalid time format! Use: HH:MM (e.g., 09:00 for 9 AM)\nYour timezone: {sub_timezone}",
                ephemeral=True
            )
            return
    elif deadline_hours:
        # Calculate based on current time in user's timezone
        now = datetime.datetime.now(user_tz)
        deadline = now + datetime.timedelta(hours=deadline_hours)
    
    # Handle auto-punishment setup
    auto_punishment_id = None
    if auto_punish and deadline:
        # Check if dominant has any punishments
        punishments = await db.get_punishments(interaction.user.id)
        if not punishments:
            await interaction.response.send_message(
                "❌ Auto-punish enabled but you have no punishments created! Create one first with /punishment_create",
                ephemeral=True
            )
            return
        # We'll store a flag to assign random punishment on deadline miss
        auto_punishment_id = -1  # Special flag for random punishment
    
    # Create task
    task_id = await db.create_task(
        submissive.id,
        interaction.user.id,
        title,
        description,
        frequency.value,
        points,
        deadline,
        recurring,
        interval_hours,
        days_of_week_str,
        time_of_day,
        auto_punishment_id,
        deadline_time  # Store the deadline_time for automatic reset on approval
    )
    
    embed = discord.Embed(
        title="📋 New Task Created",
        description=f"Task assigned to {submissive.mention}",
        color=discord.Color.green()
    )
    embed.add_field(name="Title", value=title, inline=False)
    embed.add_field(name="Description", value=description, inline=False)
    embed.add_field(name="Frequency", value=frequency.value.capitalize(), inline=True)
    embed.add_field(name="Points", value=str(points), inline=True)
    
    if auto_punish:
        embed.add_field(name="⚠️ Auto-Punish", value="Random punishment on deadline miss", inline=False)
    
    # Show recurrence info
    if recurring:
        recur_info = "🔄 **Auto-Reset Enabled**\n"
        if frequency.value == 'weekly' and days_of_week_str:
            day_names = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun']
            days = [day_names[int(d)] for d in days_of_week_str.split(',')]
            recur_info += f"Days: {', '.join(days)}"
        elif frequency.value == 'custom' and interval_hours:
            recur_info += f"Every {interval_hours} hours"
        elif frequency.value == 'daily':
            recur_info += "Resets daily"
        
        if time_of_day:
            recur_info += f" at {time_of_day}"
        
        embed.add_field(name="Recurrence", value=recur_info, inline=False)
    
    if deadline:
        embed.add_field(name="Deadline", value=f"<t:{int(deadline.timestamp())}:R>", inline=False)
    embed.set_footer(text=f"Task ID: {task_id}")
    
    await interaction.response.send_message(embed=embed)
    
    # Post to task channel if configured
    if config.TASK_CHANNEL_NAME and interaction.guild:
        await post_to_channel(interaction.guild, config.TASK_CHANNEL_NAME, embed)
    
    # Notify submissive via DM
    try:
        deadline_text = f"\n⏰ **Deadline:** <t:{int(deadline.timestamp())}:R>" if deadline else ""
        await submissive.send(f"📋 **New task assigned by {interaction.user.display_name}!**\n\n**{title}**\n{description}\n\nFrequency: {frequency.value} | Points: {points}{deadline_text}")
    except:
        pass  # User has DMs disabled

@bot.tree.command(name="tasks", description="View your tasks or a submissive's tasks")
@app_commands.describe(submissive="View tasks for this submissive (dominants only)")
async def tasks(interaction: discord.Interaction, submissive: discord.Member = None):
    """View tasks."""
    user = await db.get_user(interaction.user.id)
    if not user:
        await interaction.response.send_message(
            "❌ You need to register first! Use `/register`",
            ephemeral=True
        )
        return
    
    # Determine whose tasks to show
    if submissive:
        # Dominant viewing submissive's tasks
        if user['role'] != 'dominant':
            await interaction.response.send_message(
                "❌ Only dominants can view others' tasks!",
                ephemeral=True
            )
            return
        
        submissives = await db.get_submissives(interaction.user.id)
        if not any(s['user_id'] == submissive.id for s in submissives):
            await interaction.response.send_message(
                f"❌ {submissive.mention} is not linked to you!",
                ephemeral=True
            )
            return
        
        target_id = submissive.id
        target_name = submissive.display_name
    else:
        # User viewing own tasks
        if user['role'] == 'dominant':
            await interaction.response.send_message(
                "❌ Specify a submissive to view their tasks!",
                ephemeral=True
            )
            return
        target_id = interaction.user.id
        target_name = "Your"
    
    # Get tasks
    tasks_list = await db.get_tasks(target_id)
    
    if not tasks_list:
        await interaction.response.send_message(
            f"{target_name} tasks list is empty!",
            ephemeral=True
        )
        return
    
    embed = discord.Embed(
        title=f"📋 {target_name} Active Tasks",
        color=discord.Color.blue()
    )
    
    for task in tasks_list:
        value = f"{task['description']}\n**Frequency:** {task['frequency'].capitalize()}\n**Points:** {task['point_value']}"
        
        # Add recurrence info if enabled
        if task.get('recurrence_enabled'):
            recur_parts = []
            if task['frequency'] == 'weekly' and task.get('days_of_week'):
                day_names = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun']
                days = [day_names[int(d)] for d in task['days_of_week'].split(',')]
                recur_parts.append(f"Days: {', '.join(days)}")
            elif task['frequency'] == 'custom' and task.get('recurrence_interval_hours'):
                recur_parts.append(f"Every {task['recurrence_interval_hours']}h")
            
            if task.get('time_of_day'):
                recur_parts.append(f"at {task['time_of_day']}")
            
            if recur_parts:
                value += f"\n🔄 {' '.join(recur_parts)}"
        
        # Add deadline if exists
        if task.get('deadline'):
            deadline_dt = datetime.datetime.fromisoformat(task['deadline'])
            value += f"\n⏰ Deadline: <t:{int(deadline_dt.timestamp())}:R>"
        
        embed.add_field(
            name=f"{task['id']}. {task['title']}",
            value=value,
            inline=False
        )
    
    await interaction.response.send_message(embed=embed)

@bot.tree.command(name="task_complete", description="Submit a task completion with proof")
@app_commands.describe(
    task_id="The ID of the task to complete",
    proof="Image proof of task completion (required for submissives)"
)
async def task_complete(interaction: discord.Interaction, task_id: int, proof: discord.Attachment = None):
    """Submit task completion for approval (submissives must provide proof)."""
    user = await db.get_user(interaction.user.id)
    if not user or user['role'] != 'submissive':
        await interaction.response.send_message(
            "❌ Only submissives can complete tasks!",
            ephemeral=True
        )
        return
    
    # Require proof for submissives
    if not proof:
        await interaction.response.send_message(
            "❌ You must attach image proof to complete this task!\nUse: `/task_complete task_id:<id> proof:<attach image>`",
            ephemeral=True
        )
        return
    
    # Validate it's an image
    if not proof.content_type or not proof.content_type.startswith('image/'):
        await interaction.response.send_message(
            "❌ Proof must be an image file!",
            ephemeral=True
        )
        return
    
    # Submit for approval
    completion_id = await db.submit_task_completion(task_id, interaction.user.id, proof.url)
    if completion_id is None:
        await interaction.response.send_message(
            "❌ Task not found or already submitted!",
            ephemeral=True
        )
        return
    
    embed = discord.Embed(
        title="📤 Task Submitted for Approval",
        description="Your task completion has been submitted to your dominant for review.",
        color=discord.Color.orange()
    )
    embed.add_field(name="Task ID", value=str(task_id), inline=True)
    embed.add_field(name="Completion ID", value=str(completion_id), inline=True)
    embed.set_image(url=proof.url)
    embed.set_footer(text="You'll be notified when it's approved or rejected")
    
    await interaction.response.send_message(embed=embed)
    
    # Notify dominant
    dominant = await db.get_dominant(interaction.user.id)
    if dominant:
        try:
            dom_user = await bot.fetch_user(dominant['user_id'])
            notif_embed = discord.Embed(
                title="📥 Pending Task Approval",
                description=f"**{interaction.user.display_name}** submitted a task completion.",
                color=discord.Color.blue()
            )
            notif_embed.add_field(name="Task ID", value=str(task_id), inline=True)
            notif_embed.add_field(name="Completion ID", value=str(completion_id), inline=True)
            notif_embed.set_image(url=proof.url)
            notif_embed.set_footer(text=f"Use /approve {completion_id} or /reject {completion_id}")
            await dom_user.send(embed=notif_embed)
        except:
            pass

@bot.tree.command(name="task_delete", description="Delete a task")
@app_commands.describe(task_id="The ID of the task to delete")
async def task_delete(interaction: discord.Interaction, task_id: int):
    """Delete a task (dominant only)."""
    user = await db.get_user(interaction.user.id)
    if not user or user['role'] != 'dominant':
        await interaction.response.send_message(
            "❌ Only dominants can delete tasks!",
            ephemeral=True
        )
        return
    
    success = await db.delete_task(task_id, interaction.user.id)
    if success:
        embed = discord.Embed(
            title="🗑️ Task Deleted",
            description=f"Task #{task_id} has been permanently deleted.",
            color=discord.Color.orange()
        )
        await interaction.response.send_message(embed=embed)
    else:
        await interaction.response.send_message(
            "❌ Task not found or you don't have permission to delete it!",
            ephemeral=True
        )

@bot.tree.command(name="task_edit", description="Edit an existing task")
@app_commands.describe(
    task_id="The ID of the task to edit",
    title="New task title (optional)",
    description="New task description (optional)",
    points="New point value (optional)",
    deadline_hours="New deadline in hours (optional)",
    deadline_datetime="New specific deadline YYYY-MM-DD HH:MM (optional)"
)
async def task_edit(
    interaction: discord.Interaction,
    task_id: int,
    title: str = None,
    description: str = None,
    points: int = None,
    deadline_hours: int = None,
    deadline_datetime: str = None
):
    """Edit a task (dominant only)."""
    user = await db.get_user(interaction.user.id)
    if not user or user['role'] != 'dominant':
        await interaction.response.send_message(
            "❌ Only dominants can edit tasks!",
            ephemeral=True
        )
        return
    
    # Calculate new deadline if provided
    new_deadline = None
    if deadline_datetime:
        try:
            new_deadline = datetime.datetime.strptime(deadline_datetime, "%Y-%m-%d %H:%M")
        except ValueError:
            await interaction.response.send_message(
                "❌ Invalid datetime format! Use: YYYY-MM-DD HH:MM (e.g., 2026-02-05 15:30)",
                ephemeral=True
            )
            return
    elif deadline_hours:
        new_deadline = datetime.datetime.now() + datetime.timedelta(hours=deadline_hours)
    
    success = await db.edit_task(
        task_id, 
        interaction.user.id, 
        title=title, 
        description=description, 
        point_value=points,
        deadline=new_deadline
    )
    
    if success:
        embed = discord.Embed(
            title="✏️ Task Updated",
            description=f"Task #{task_id} has been updated.",
            color=discord.Color.blue()
        )
        
        if title:
            embed.add_field(name="New Title", value=title, inline=False)
        if description:
            embed.add_field(name="New Description", value=description, inline=False)
        if points:
            embed.add_field(name="New Points", value=str(points), inline=True)
        if new_deadline:
            embed.add_field(name="New Deadline", value=f"<t:{int(new_deadline.timestamp())}:R>", inline=True)
        
        await interaction.response.send_message(embed=embed)
    else:
        await interaction.response.send_message(
            "❌ Task not found or you don't have permission to edit it!",
            ephemeral=True
        )

# ============ REWARD COMMANDS ============

@bot.tree.command(name="reward_create", description="Create a new reward")
@app_commands.describe(
    title="Reward title",
    description="Reward description",
    cost="Point cost (default: 0)"
)
async def reward_create(
    interaction: discord.Interaction,
    title: str,
    description: str,
    cost: int = 0
):
    """Create a reward (dominant only)."""
    user = await db.get_user(interaction.user.id)
    if not user or user['role'] != 'dominant':
        await interaction.response.send_message(
            "❌ Only dominants can create rewards!",
            ephemeral=True
        )
        return
    
    reward_id = await db.create_reward(interaction.user.id, title, description, cost)
    
    embed = discord.Embed(
        title="🎁 Reward Created",
        color=discord.Color.gold()
    )
    embed.add_field(name="Title", value=title, inline=False)
    embed.add_field(name="Description", value=description, inline=False)
    embed.add_field(name="Cost", value=f"{cost} points", inline=True)
    embed.set_footer(text=f"Reward ID: {reward_id}")
    
    await interaction.response.send_message(embed=embed)

@bot.tree.command(name="rewards", description="View available rewards")
async def rewards(interaction: discord.Interaction):
    """View rewards."""
    user = await db.get_user(interaction.user.id)
    if not user:
        await interaction.response.send_message(
            "❌ You need to register first! Use `/register`",
            ephemeral=True
        )
        return
    
    # Get dominant ID(s)
    if user['role'] == 'dominant':
        dominant_ids = [interaction.user.id]
    else:
        dominants = await db.get_dominants(interaction.user.id)
        if not dominants:
            await interaction.response.send_message(
                "❌ You're not linked to a dominant!",
                ephemeral=True
            )
            return
        dominant_ids = [d['user_id'] for d in dominants]
    
    # Collect rewards from all dominants
    all_rewards = []
    for dominant_id in dominant_ids:
        rewards_list = await db.get_rewards(dominant_id)
        all_rewards.extend(rewards_list)
    
    if not all_rewards:
        await interaction.response.send_message(
            "No rewards available yet!",
            ephemeral=True
        )
        return
    
    embed = discord.Embed(
        title="🎁 Available Rewards",
        color=discord.Color.gold()
    )
    
    for reward in all_rewards:
        value = f"{reward['description']}\n**Cost:** {reward['point_cost']} points"
        embed.add_field(
            name=f"{reward['id']}. {reward['title']}",
            value=value,
            inline=False
        )
    
    await interaction.response.send_message(embed=embed)

@bot.tree.command(name="reward_assign", description="Assign a reward to a submissive")
@app_commands.describe(
    submissive="The submissive to reward",
    reward_id="The reward ID",
    reason="Reason for the reward (optional)"
)
async def reward_assign(
    interaction: discord.Interaction,
    submissive: discord.Member,
    reward_id: int,
    reason: str = None
):
    """Assign a reward and deduct points (dominant only)."""
    user = await db.get_user(interaction.user.id)
    if not user or user['role'] != 'dominant':
        await interaction.response.send_message(
            "❌ Only dominants can assign rewards!",
            ephemeral=True
        )
        return
    
    # Get reward details
    import aiosqlite
    async with aiosqlite.connect(db.DATABASE_NAME) as database:
        database.row_factory = aiosqlite.Row
        async with database.execute(
            "SELECT * FROM rewards WHERE id = ? AND dominant_id = ?",
            (reward_id, interaction.user.id)
        ) as cursor:
            reward = await cursor.fetchone()
            if not reward:
                await interaction.response.send_message(
                    "❌ Reward not found!",
                    ephemeral=True
                )
                return
            reward = dict(reward)
    
    # Check if submissive can afford it
    sub_user = await db.get_user(submissive.id)
    if not sub_user:
        await interaction.response.send_message(
            "❌ Submissive not registered!",
            ephemeral=True
        )
        return
    
    if sub_user['points'] < reward['point_cost']:
        await interaction.response.send_message(
            f"❌ {submissive.mention} doesn't have enough points! (Has: {sub_user['points']}, Needs: {reward['point_cost']})",
            ephemeral=True
        )
        return
    
    # Deduct points
    new_total = await db.update_points(submissive.id, -reward['point_cost'])
    
    # Assign reward
    await db.assign_reward(submissive.id, interaction.user.id, reward_id, reason)
    
    embed = discord.Embed(
        title="🎁 Reward Assigned",
        description=f"Reward given to {submissive.mention}",
        color=discord.Color.gold()
    )
    embed.add_field(name="Reward", value=reward['title'], inline=False)
    embed.add_field(name="Cost", value=f"-{reward['point_cost']} points", inline=True)
    embed.add_field(name="New Balance", value=f"{new_total} points", inline=True)
    if reason:
        embed.add_field(name="Reason", value=reason, inline=False)
    
    await interaction.response.send_message(embed=embed)
    
    # Notify submissive
    try:
        notif = discord.Embed(
            title="🎉 Reward Received!",
            description=f"**{interaction.user.display_name}** has given you a reward!",
            color=discord.Color.gold()
        )
        notif.add_field(name="Reward", value=reward['title'], inline=False)
        notif.add_field(name="Description", value=reward['description'], inline=False)
        notif.add_field(name="Cost", value=f"-{reward['point_cost']} points", inline=True)
        notif.add_field(name="New Balance", value=f"{new_total} points", inline=True)
        if reason:
            notif.add_field(name="Reason", value=reason, inline=False)
        await submissive.send(embed=notif)
    except:
        pass

@bot.tree.command(name="reward_delete", description="Delete a reward")
@app_commands.describe(reward_id="The ID of the reward to delete")
async def reward_delete(interaction: discord.Interaction, reward_id: int):
    """Delete a reward (dominant only)."""
    user = await db.get_user(interaction.user.id)
    if not user or user['role'] != 'dominant':
        await interaction.response.send_message(
            "❌ Only dominants can delete rewards!",
            ephemeral=True
        )
        return
    
    success = await db.delete_reward(reward_id, interaction.user.id)
    if success:
        embed = discord.Embed(
            title="🗑️ Reward Deleted",
            description=f"Reward #{reward_id} has been permanently deleted.",
            color=discord.Color.orange()
        )
        await interaction.response.send_message(embed=embed)
    else:
        await interaction.response.send_message(
            "❌ Reward not found or you don't have permission to delete it!",
            ephemeral=True
        )

@bot.tree.command(name="reward_edit", description="Edit an existing reward")
@app_commands.describe(
    reward_id="The ID of the reward to edit",
    title="New reward title (optional)",
    description="New reward description (optional)",
    cost="New point cost (optional)"
)
async def reward_edit(
    interaction: discord.Interaction,
    reward_id: int,
    title: str = None,
    description: str = None,
    cost: int = None
):
    """Edit a reward (dominant only)."""
    user = await db.get_user(interaction.user.id)
    if not user or user['role'] != 'dominant':
        await interaction.response.send_message(
            "❌ Only dominants can edit rewards!",
            ephemeral=True
        )
        return
    
    success = await db.edit_reward(reward_id, interaction.user.id, title=title, description=description, point_cost=cost)
    
    if success:
        embed = discord.Embed(
            title="✏️ Reward Updated",
            description=f"Reward #{reward_id} has been updated.",
            color=discord.Color.gold()
        )
        
        if title:
            embed.add_field(name="New Title", value=title, inline=False)
        if description:
            embed.add_field(name="New Description", value=description, inline=False)
        if cost is not None:
            embed.add_field(name="New Cost", value=f"{cost} points", inline=True)
        
        await interaction.response.send_message(embed=embed)
    else:
        await interaction.response.send_message(
            "❌ Reward not found or you don't have permission to edit it!",
            ephemeral=True
        )

# ============ PUNISHMENT COMMANDS ============

@bot.tree.command(name="punishment_create", description="Create a new punishment")
@app_commands.describe(
    title="Punishment title",
    description="Punishment description"
)
async def punishment_create(
    interaction: discord.Interaction,
    title: str,
    description: str
):
    """Create a punishment (dominant only)."""
    user = await db.get_user(interaction.user.id)
    if not user or user['role'] != 'dominant':
        await interaction.response.send_message(
            "❌ Only dominants can create punishments!",
            ephemeral=True
        )
        return
    
    punishment_id = await db.create_punishment(interaction.user.id, title, description)
    
    embed = discord.Embed(
        title="⚠️ Punishment Created",
        color=discord.Color.red()
    )
    embed.add_field(name="Title", value=title, inline=False)
    embed.add_field(name="Description", value=description, inline=False)
    embed.set_footer(text=f"Punishment ID: {punishment_id}")
    
    await interaction.response.send_message(embed=embed)

@bot.tree.command(name="punishments", description="View available punishments")
async def punishments(interaction: discord.Interaction):
    """View punishments."""
    user = await db.get_user(interaction.user.id)
    if not user:
        await interaction.response.send_message(
            "❌ You need to register first! Use `/register`",
            ephemeral=True
        )
        return
    
    # Get dominant ID(s)
    if user['role'] == 'dominant':
        dominant_ids = [interaction.user.id]
    else:
        dominants = await db.get_dominants(interaction.user.id)
        if not dominants:
            await interaction.response.send_message(
                "❌ You're not linked to a dominant!",
                ephemeral=True
            )
            return
        dominant_ids = [d['user_id'] for d in dominants]
    
    # Collect punishments from all dominants
    all_punishments = []
    for dominant_id in dominant_ids:
        punishments_list = await db.get_punishments(dominant_id)
        all_punishments.extend(punishments_list)
    
    if not all_punishments:
        await interaction.response.send_message(
            "No punishments available yet!",
            ephemeral=True
        )
        return
    
    embed = discord.Embed(
        title="⚠️ Available Punishments",
        color=discord.Color.red()
    )
    
    for punishment in all_punishments:
        embed.add_field(
            name=f"{punishment['id']}. {punishment['title']}",
            value=punishment['description'],
            inline=False
        )
    
    await interaction.response.send_message(embed=embed)

@bot.tree.command(name="punishment_delete", description="Delete a punishment")
@app_commands.describe(punishment_id="The ID of the punishment to delete")
async def punishment_delete(interaction: discord.Interaction, punishment_id: int):
    """Delete a punishment (dominant only)."""
    user = await db.get_user(interaction.user.id)
    if not user or user['role'] != 'dominant':
        await interaction.response.send_message(
            "❌ Only dominants can delete punishments!",
            ephemeral=True
        )
        return
    
    success = await db.delete_punishment(punishment_id, interaction.user.id)
    if success:
        embed = discord.Embed(
            title="🗑️ Punishment Deleted",
            description=f"Punishment #{punishment_id} has been permanently deleted.",
            color=discord.Color.orange()
        )
        await interaction.response.send_message(embed=embed)
    else:
        await interaction.response.send_message(
            "❌ Punishment not found or you don't have permission to delete it!",
            ephemeral=True
        )

@bot.tree.command(name="punishment_edit", description="Edit an existing punishment")
@app_commands.describe(
    punishment_id="The ID of the punishment to edit",
    title="New punishment title (optional)",
    description="New punishment description (optional)"
)
async def punishment_edit(
    interaction: discord.Interaction,
    punishment_id: int,
    title: str = None,
    description: str = None
):
    """Edit a punishment (dominant only)."""
    user = await db.get_user(interaction.user.id)
    if not user or user['role'] != 'dominant':
        await interaction.response.send_message(
            "❌ Only dominants can edit punishments!",
            ephemeral=True
        )
        return
    
    success = await db.edit_punishment(punishment_id, interaction.user.id, title=title, description=description)
    
    if success:
        embed = discord.Embed(
            title="✏️ Punishment Updated",
            description=f"Punishment #{punishment_id} has been updated.",
            color=discord.Color.red()
        )
        
        if title:
            embed.add_field(name="New Title", value=title, inline=False)
        if description:
            embed.add_field(name="New Description", value=description, inline=False)
        
        await interaction.response.send_message(embed=embed)
    else:
        await interaction.response.send_message(
            "❌ Punishment not found or you don't have permission to edit it!",
            ephemeral=True
        )

@bot.tree.command(name="punishment_assign", description="Assign a punishment to a submissive")
@app_commands.describe(
    submissive="The submissive to punish",
    punishment_id="The punishment ID",
    reason="Reason for the punishment (optional)",
    deadline_hours="Hours to complete (default: 24)",
    deadline_datetime="Specific deadline (YYYY-MM-DD HH:MM format, e.g., 2026-02-05 15:30)",
    point_penalty="Points deducted if not completed (default: 10)",
    forward_to="User who will receive the proof image (optional)"
)
async def punishment_assign(
    interaction: discord.Interaction,
    submissive: discord.Member,
    punishment_id: int,
    reason: str = None,
    deadline_hours: int = 24,
    deadline_datetime: str = None,
    point_penalty: int = 10,
    forward_to: discord.Member = None
):
    """Assign a punishment with proof requirement and deadline (dominant only)."""
    user = await db.get_user(interaction.user.id)
    if not user or user['role'] != 'dominant':
        await interaction.response.send_message(
            "❌ Only dominants can assign punishments!",
            ephemeral=True
        )
        return
    
    # Calculate deadline - prioritize specific datetime over hours
    if deadline_datetime:
        try:
            deadline = datetime.datetime.strptime(deadline_datetime, "%Y-%m-%d %H:%M")
        except ValueError:
            await interaction.response.send_message(
                "❌ Invalid datetime format! Use: YYYY-MM-DD HH:MM (e.g., 2026-02-05 15:30)",
                ephemeral=True
            )
            return
    else:
        deadline = datetime.datetime.now() + datetime.timedelta(hours=deadline_hours)
    
    forward_to_id = forward_to.id if forward_to else None
    assignment_id = await db.assign_punishment(
        submissive.id, 
        interaction.user.id, 
        punishment_id, 
        reason, 
        deadline, 
        point_penalty,
        forward_to_id
    )
    
    embed = discord.Embed(
        title="⚠️ Punishment Assigned",
        description=f"Punishment assigned to {submissive.mention}",
        color=discord.Color.red()
    )
    embed.add_field(name="Punishment ID", value=str(punishment_id), inline=True)
    embed.add_field(name="Assignment ID", value=str(assignment_id), inline=True)
    embed.add_field(name="Deadline", value=f"<t:{int(deadline.timestamp())}:R>", inline=False)
    embed.add_field(name="Point Penalty", value=f"{point_penalty} (doubles if late)", inline=True)
    if reason:
        embed.add_field(name="Reason", value=reason, inline=False)
    if forward_to:
        embed.add_field(name="📸 Image Forward", value=f"Proof will be sent to {forward_to.mention}", inline=False)
    
    await interaction.response.send_message(embed=embed)
    
    # Post to punishment channel if configured
    if config.PUNISHMENT_CHANNEL_NAME and interaction.guild:
        await post_to_channel(interaction.guild, config.PUNISHMENT_CHANNEL_NAME, embed)
    
    # Notify submissive via DM
    try:
        notif = discord.Embed(
            title="⚠️ Punishment Assigned",
            description=f"**{interaction.user.display_name}** has assigned you a punishment.",
            color=discord.Color.red()
        )
        notif.add_field(name="Assignment ID", value=str(assignment_id), inline=True)
        notif.add_field(name="Deadline", value=f"<t:{int(deadline.timestamp())}:R>", inline=False)
        notif.add_field(name="Point Penalty", value=f"-{point_penalty} points (doubles to -{point_penalty * 2} if late!)", inline=False)
        if reason:
            notif.add_field(name="Reason", value=reason, inline=False)
        if forward_to:
            notif.add_field(name="📸 Image Forward", value=f"⚠️ Your proof will be sent to {forward_to.display_name}", inline=False)
        notif.set_footer(text=f"Submit proof with: /punishment_complete {assignment_id} proof:<image>")
        await submissive.send(embed=notif)
        print(f"[DM] Sent punishment notification to {submissive.display_name}")
    except discord.Forbidden:
        print(f"[DM] User {submissive.display_name} has DMs disabled")
    except Exception as e:
        print(f"[DM] Failed to send DM to {submissive.display_name}: {e}")

@bot.tree.command(name="punishment_complete", description="Submit proof of punishment completion")
@app_commands.describe(
    assignment_id="The punishment assignment ID",
    proof="Image proof of punishment completion (required)"
)
async def punishment_complete(interaction: discord.Interaction, assignment_id: int, proof: discord.Attachment):
    """Submit proof of punishment completion."""
    user = await db.get_user(interaction.user.id)
    if not user or user['role'] != 'submissive':
        await interaction.response.send_message(
            "❌ Only submissives can complete punishments!",
            ephemeral=True
        )
        return
    
    # Require proof
    if not proof or not proof.content_type or not proof.content_type.startswith('image/'):
        await interaction.response.send_message(
            "❌ You must attach image proof!",
            ephemeral=True
        )
        return
    
    # Submit proof
    await db.submit_punishment_proof(assignment_id, proof.url)
    
    # Check if there's a forward user (will be sent after approval)
    forward_user_id = await db.get_punishment_forward_user(assignment_id)
    has_forward = forward_user_id is not None
    
    embed = discord.Embed(
        title="📤 Punishment Proof Submitted",
        description="Your punishment completion proof has been submitted for review.",
        color=discord.Color.orange()
    )
    embed.add_field(name="Assignment ID", value=str(assignment_id), inline=True)
    if has_forward:
        embed.add_field(name="📸 Image Forward", value="⏳ Will be sent after approval", inline=True)
    embed.set_image(url=proof.url)
    embed.set_footer(text="You'll be notified when reviewed")
    
    await interaction.response.send_message(embed=embed)
    
    # Notify dominant
    dominant = await db.get_dominant(interaction.user.id)
    if dominant:
        try:
            dom_user = await bot.fetch_user(dominant['user_id'])
            notif = discord.Embed(
                title="📥 Punishment Proof Submitted",
                description=f"**{interaction.user.display_name}** submitted punishment proof.",
                color=discord.Color.blue()
            )
            notif.add_field(name="Assignment ID", value=str(assignment_id), inline=True)
            if has_forward:
                notif.add_field(name="📸 Forward Pending", value="Will be sent after approval", inline=True)
            notif.set_image(url=proof.url)
            notif.set_footer(text=f"Use /punishment_approve {assignment_id} or /punishment_reject {assignment_id}")
            await dom_user.send(embed=notif)
        except:
            pass

@bot.tree.command(name="punishment_approve", description="Approve a punishment completion")
@app_commands.describe(assignment_id="The punishment assignment ID")
async def punishment_approve(interaction: discord.Interaction, assignment_id: int):
    """Approve punishment completion (dominant only)."""
    user = await db.get_user(interaction.user.id)
    if not user or user['role'] != 'dominant':
        await interaction.response.send_message(
            "❌ Only dominants can approve punishments!",
            ephemeral=True
        )
        return
    
    refund_penalty = await db.approve_punishment_completion(assignment_id, interaction.user.id, True)
    if refund_penalty is None:
        await interaction.response.send_message(
            "❌ Punishment not found or already reviewed!",
            ephemeral=True
        )
        return
    
    # Get assignment details including forward user and proof URL
    import aiosqlite
    async with aiosqlite.connect(db.DATABASE_NAME) as database:
        database.row_factory = aiosqlite.Row
        async with database.execute(
            "SELECT submissive_id, point_penalty, forward_to_user_id, proof_url FROM assigned_rewards_punishments WHERE id = ?",
            (assignment_id,)
        ) as cursor:
            row = await cursor.fetchone()
            if row:
                submissive_id = row[0]
                penalty = row[1]
                forward_user_id = row[2]
                proof_url = row[3]
                
                # Forward image to designated user if specified (ONLY on approval)
                forwarded = False
                if forward_user_id and proof_url:
                    try:
                        forward_user = await bot.fetch_user(forward_user_id)
                        sub_user_obj = await bot.fetch_user(submissive_id)
                        forward_embed = discord.Embed(
                            title="📸 Punishment Proof Received",
                            description=f"**{sub_user_obj.display_name}** completed a punishment and it was approved.",
                            color=discord.Color.purple()
                        )
                        forward_embed.add_field(name="Submissive", value=f"{sub_user_obj.display_name}", inline=True)
                        forward_embed.set_image(url=proof_url)
                        forward_embed.set_footer(text=f"Assignment ID: {assignment_id}")
                        await forward_user.send(embed=forward_embed)
                        forwarded = True
                    except:
                        pass
                
                # If it was late, refund the penalty
                if refund_penalty > 0:
                    new_total = await db.update_points(submissive_id, refund_penalty)
                    desc = f"Punishment #{assignment_id} approved.\n✨ **Late penalty refunded!**"
                else:
                    new_total = await db.get_user(submissive_id)
                    new_total = new_total['points'] if new_total else 0
                    desc = f"Punishment #{assignment_id} approved."
                
                if forwarded:
                    desc += "\n📸 **Image forwarded to designated user**"
                
                embed = discord.Embed(
                    title="✅ Punishment Approved",
                    description=desc,
                    color=discord.Color.green()
                )
                if refund_penalty > 0:
                    embed.add_field(name="Refunded", value=f"+{refund_penalty} points", inline=True)
                if forwarded:
                    embed.add_field(name="Forwarded", value="✅ Image sent", inline=True)
                
                await interaction.response.send_message(embed=embed)
                
                # Notify submissive
                try:
                    sub_user = await bot.fetch_user(submissive_id)
                    notif_desc = f"Your punishment completion was approved!"
                    if refund_penalty > 0:
                        notif_desc += f"\n🎉 **Penalty refunded: +{refund_penalty} points!**"
                    if forwarded:
                        notif_desc += f"\n📸 **Your proof was forwarded**"
                    
                    notif = discord.Embed(
                        title="✅ Punishment Approved",
                        description=notif_desc,
                        color=discord.Color.green()
                    )
                    notif.add_field(name="Total Points", value=str(new_total), inline=True)
                    await sub_user.send(embed=notif)
                except:
                    pass

@bot.tree.command(name="punishment_reject", description="Reject a punishment completion")
@app_commands.describe(
    assignment_id="The punishment assignment ID",
    reason="Reason for rejection"
)
async def punishment_reject(interaction: discord.Interaction, assignment_id: int, reason: str = None):
    """Reject punishment completion (dominant only)."""
    user = await db.get_user(interaction.user.id)
    if not user or user['role'] != 'dominant':
        await interaction.response.send_message(
            "❌ Only dominants can reject punishments!",
            ephemeral=True
        )
        return
    
    result = await db.approve_punishment_completion(assignment_id, interaction.user.id, False)
    if result is None:
        await interaction.response.send_message(
            "❌ Punishment not found or already reviewed!",
            ephemeral=True
        )
        return
    
    embed = discord.Embed(
        title="❌ Punishment Rejected",
        description=f"Punishment #{assignment_id} rejected.",
        color=discord.Color.red()
    )
    if reason:
        embed.add_field(name="Reason", value=reason, inline=False)
    
    await interaction.response.send_message(embed=embed)
    
    # Notify submissive
    import aiosqlite
    async with aiosqlite.connect(db.DATABASE_NAME) as database:
        database.row_factory = aiosqlite.Row
        async with database.execute(
            "SELECT submissive_id FROM assigned_rewards_punishments WHERE id = ?",
            (assignment_id,)
        ) as cursor:
            row = await cursor.fetchone()
            if row:
                try:
                    sub_user = await bot.fetch_user(row[0])
                    notif = discord.Embed(
                        title="❌ Punishment Rejected",
                        description="Your punishment proof was rejected. You must resubmit.",
                        color=discord.Color.red()
                    )
                    if reason:
                        notif.add_field(name="Reason", value=reason, inline=False)
                    await sub_user.send(embed=notif)
                except:
                    pass

@bot.tree.command(name="punishment_cancel", description="Cancel a punishment (no resubmission required)")
@app_commands.describe(
    assignment_id="The punishment assignment ID",
    reason="Reason for cancellation"
)
async def punishment_cancel(interaction: discord.Interaction, assignment_id: int, reason: str = None):
    """Cancel punishment - marks as rejected but no resubmission needed (dominant only)."""
    user = await db.get_user(interaction.user.id)
    if not user or user['role'] != 'dominant':
        await interaction.response.send_message(
            "❌ Only dominants can cancel punishments!",
            ephemeral=True
        )
        return
    
    result = await db.approve_punishment_completion(assignment_id, interaction.user.id, False)
    if result is None:
        await interaction.response.send_message(
            "❌ Punishment not found or already reviewed!",
            ephemeral=True
        )
        return
    
    embed = discord.Embed(
        title="❌ Punishment Cancelled",
        description=f"Punishment #{assignment_id} has been cancelled.\nNo resubmission required.",
        color=discord.Color.orange()
    )
    if reason:
        embed.add_field(name="Reason", value=reason, inline=False)
    
    await interaction.response.send_message(embed=embed)
    
    # Notify submissive
    import aiosqlite
    async with aiosqlite.connect(db.DATABASE_NAME) as database:
        database.row_factory = aiosqlite.Row
        async with database.execute(
            "SELECT submissive_id FROM assigned_rewards_punishments WHERE id = ?",
            (assignment_id,)
        ) as cursor:
            row = await cursor.fetchone()
            if row:
                try:
                    sub_user = await bot.fetch_user(row[0])
                    notif = discord.Embed(
                        title="❌ Punishment Cancelled",
                        description="Your punishment has been cancelled by your dominant.\n✅ **No resubmission needed.**",
                        color=discord.Color.orange()
                    )
                    if reason:
                        notif.add_field(name="Reason", value=reason, inline=False)
                    await sub_user.send(embed=notif)
                except:
                    pass

@bot.tree.command(name="punishment_remind", description="Send a reminder to submissive about active punishment")
@app_commands.describe(
    assignment_id="The punishment assignment ID to remind about"
)
async def punishment_remind(interaction: discord.Interaction, assignment_id: int):
    """Send a reminder DM to submissive about their punishment (dominant only)."""
    user = await db.get_user(interaction.user.id)
    if not user or user['role'] != 'dominant':
        await interaction.response.send_message(
            "❌ Only dominants can send reminders!",
            ephemeral=True
        )
        return
    
    # Get punishment assignment details
    import aiosqlite
    async with aiosqlite.connect(db.DATABASE_NAME) as database:
        database.row_factory = aiosqlite.Row
        async with database.execute("""
            SELECT ap.*, p.title, p.description
            FROM assigned_rewards_punishments ap
            JOIN punishments p ON ap.item_id = p.id
            WHERE ap.id = ? AND ap.type = 'punishment' AND ap.dominant_id = ? AND ap.completion_status = 'pending'
        """, (assignment_id, interaction.user.id)) as cursor:
            row = await cursor.fetchone()
            if not row:
                await interaction.response.send_message(
                    "❌ Punishment assignment not found, already completed, or you don't own it!",
                    ephemeral=True
                )
                return
            
            assignment = dict(row)
    
    # Send reminder to submissive
    try:
        sub_user = await bot.fetch_user(assignment['submissive_id'])
        
        deadline_ts = int(datetime.datetime.fromisoformat(assignment['deadline']).timestamp()) if assignment['deadline'] else 0
        
        reminder = discord.Embed(
            title="⏰ Punishment Reminder",
            description=f"🔔 **Reminder from {interaction.user.display_name}**\n\nYou have a pending punishment:\n\n**{assignment['title']}**\n{assignment['description']}",
            color=discord.Color.orange()
        )
        reminder.add_field(name="Assignment ID", value=str(assignment_id), inline=True)
        if deadline_ts > 0:
            reminder.add_field(name="Deadline", value=f"<t:{deadline_ts}:R>", inline=True)
        reminder.add_field(name="Point Penalty", value=f"-{assignment['point_penalty']} points (doubles if late!)", inline=True)
        if assignment['reason']:
            reminder.add_field(name="Reason", value=assignment['reason'], inline=False)
        reminder.set_footer(text=f"Submit proof with: /punishment_complete {assignment_id} proof:<image>")
        
        await sub_user.send(embed=reminder)
        
        # Confirm to dominant
        await interaction.response.send_message(
            f"✅ Reminder sent to <@{assignment['submissive_id']}>!",
            ephemeral=True
        )
    except discord.Forbidden:
        await interaction.response.send_message(
            "❌ Could not send reminder - user has DMs disabled.",
            ephemeral=True
        )
    except Exception as e:
        await interaction.response.send_message(
            f"❌ Failed to send reminder: {str(e)}",
            ephemeral=True
        )

@bot.tree.command(name="punishments_active", description="View your active punishments")
async def punishments_active(interaction: discord.Interaction):
    """View active punishments (submissive only)."""
    user = await db.get_user(interaction.user.id)
    if not user or user['role'] != 'submissive':
        await interaction.response.send_message(
            "❌ Only submissives can view active punishments!",
            ephemeral=True
        )
        return
    
    active_list = await db.get_active_punishments(interaction.user.id)
    
    if not active_list:
        await interaction.response.send_message(
            "✅ No active punishments!",
            ephemeral=True
        )
        return
    
    embed = discord.Embed(
        title="⚠️ Your Active Punishments",
        description=f"{len(active_list)} punishment(s) pending",
        color=discord.Color.red()
    )
    
    for item in active_list[:10]:
        deadline_ts = int(datetime.datetime.fromisoformat(item['deadline']).timestamp()) if item['deadline'] else 0
        value = f"**{item['title']}**\n{item['description']}\n**Penalty:** -{item['point_penalty']} points (doubles if late!)\n**Deadline:** <t:{deadline_ts}:R>"
        embed.add_field(
            name=f"Assignment ID: {item['id']}",
            value=value,
            inline=False
        )
    
    embed.set_footer(text="Submit proof with /punishment_complete <id> proof:<image>")
    await interaction.response.send_message(embed=embed)

# ============ AUTO-PUNISHMENT COMMANDS ============

@bot.tree.command(name="task_link_punishment", description="Link a punishment to auto-assign when task deadline is missed")
@app_commands.describe(
    task_id="The task ID to link",
    punishment_id="The punishment ID to auto-assign on failure"
)
async def task_link_punishment(interaction: discord.Interaction, task_id: int, punishment_id: int):
    """Link punishment to task (dominant only)."""
    user = await db.get_user(interaction.user.id)
    if not user or user['role'] != 'dominant':
        await interaction.response.send_message(
            "❌ Only dominants can link punishments!",
            ephemeral=True
        )
        return
    
    success = await db.link_task_punishment(task_id, punishment_id, interaction.user.id)
    if success:
        embed = discord.Embed(
            title="🔗 Punishment Linked to Task",
            description=f"Punishment #{punishment_id} will be auto-assigned if Task #{task_id} deadline is missed.",
            color=discord.Color.blue()
        )
        await interaction.response.send_message(embed=embed)
    else:
        await interaction.response.send_message(
            "❌ Task or punishment not found, or you don't own them!",
            ephemeral=True
        )

@bot.tree.command(name="threshold_create", description="Auto-assign punishment when points drop below threshold")
@app_commands.describe(
    threshold_points="Point threshold (punishment assigned when below this)",
    punishment_id="The punishment ID to auto-assign",
    submissive="Specific submissive (leave blank for all your submissives)"
)
async def threshold_create(
    interaction: discord.Interaction,
    threshold_points: int,
    punishment_id: int,
    submissive: discord.Member = None
):
    """Create point threshold trigger (dominant only)."""
    user = await db.get_user(interaction.user.id)
    if not user or user['role'] != 'dominant':
        await interaction.response.send_message(
            "❌ Only dominants can create thresholds!",
            ephemeral=True
        )
        return
    
    submissive_id = submissive.id if submissive else None
    threshold_id = await db.create_point_threshold(
        interaction.user.id,
        threshold_points,
        punishment_id,
        submissive_id
    )
    
    target = submissive.mention if submissive else "all your submissives"
    embed = discord.Embed(
        title="🎯 Point Threshold Created",
        description=f"Punishment #{punishment_id} will be auto-assigned to {target} when points drop below {threshold_points}.",
        color=discord.Color.orange()
    )
    embed.set_footer(text=f"Threshold ID: {threshold_id} | Triggers max once per 24 hours")
    
    await interaction.response.send_message(embed=embed)

@bot.tree.command(name="thresholds", description="View your point thresholds")
async def thresholds(interaction: discord.Interaction):
    """View point thresholds (dominant only)."""
    user = await db.get_user(interaction.user.id)
    if not user or user['role'] != 'dominant':
        await interaction.response.send_message(
            "❌ Only dominants can view thresholds!",
            ephemeral=True
        )
        return
    
    thresholds_list = await db.get_point_thresholds(interaction.user.id)
    
    if not thresholds_list:
        await interaction.response.send_message(
            "No thresholds set up yet!",
            ephemeral=True
        )
        return
    
    embed = discord.Embed(
        title="🎯 Your Point Thresholds",
        color=discord.Color.orange()
    )
    
    for t in thresholds_list:
        target = t.get('submissive_name', 'All submissives')
        value = f"**Target:** {target}\n**Punishment:** {t['punishment_title']}\n**Threshold:** < {t['threshold_points']} points"
        embed.add_field(
            name=f"ID: {t['id']}",
            value=value,
            inline=False
        )
    
    embed.set_footer(text="Delete with: /threshold_delete <id>")
    await interaction.response.send_message(embed=embed)

@bot.tree.command(name="threshold_delete", description="Delete a point threshold")
@app_commands.describe(threshold_id="The threshold ID to delete")
async def threshold_delete(interaction: discord.Interaction, threshold_id: int):
    """Delete point threshold (dominant only)."""
    user = await db.get_user(interaction.user.id)
    if not user or user['role'] != 'dominant':
        await interaction.response.send_message(
            "❌ Only dominants can delete thresholds!",
            ephemeral=True
        )
        return
    
    success = await db.delete_point_threshold(threshold_id, interaction.user.id)
    if success:
        await interaction.response.send_message("✅ Threshold deleted!", ephemeral=True)
    else:
        await interaction.response.send_message(
            "❌ Threshold not found or you don't own it!",
            ephemeral=True
        )

@bot.tree.command(name="punishment_assign_random", description="Assign a random punishment to a submissive")
@app_commands.describe(
    submissive="The submissive to punish",
    reason="Reason for punishment (optional)",
    deadline_hours="Hours to complete (default: 24)",
    deadline_datetime="Specific deadline (YYYY-MM-DD HH:MM format, e.g., 2026-02-05 15:30)",
    point_penalty="Points deducted if not completed (default: 10)",
    forward_to="User who will receive the proof image (optional)"
)
async def punishment_assign_random(
    interaction: discord.Interaction,
    submissive: discord.Member,
    reason: str = None,
    deadline_hours: int = 24,
    deadline_datetime: str = None,
    point_penalty: int = 10,
    forward_to: discord.Member = None
):
    """Assign random punishment (dominant only)."""
    user = await db.get_user(interaction.user.id)
    if not user or user['role'] != 'dominant':
        await interaction.response.send_message(
            "❌ Only dominants can assign punishments!",
            ephemeral=True
        )
        return
    
    # Get random punishment
    punishment = await db.get_random_punishment(interaction.user.id)
    if not punishment:
        await interaction.response.send_message(
            "❌ No punishments available! Create some first with /punishment_create",
            ephemeral=True
        )
        return
    
    # Calculate deadline - prioritize specific datetime over hours
    if deadline_datetime:
        try:
            deadline = datetime.datetime.strptime(deadline_datetime, "%Y-%m-%d %H:%M")
        except ValueError:
            await interaction.response.send_message(
                "❌ Invalid datetime format! Use: YYYY-MM-DD HH:MM (e.g., 2026-02-05 15:30)",
                ephemeral=True
            )
            return
    else:
        deadline = datetime.datetime.now() + datetime.timedelta(hours=deadline_hours)
    
    forward_to_id = forward_to.id if forward_to else None
    assignment_id = await db.assign_punishment(
        submissive.id,
        interaction.user.id,
        punishment['id'],
        reason or "Random punishment",
        deadline,
        point_penalty,
        forward_to_id
    )
    
    embed = discord.Embed(
        title="🎲 Random Punishment Assigned",
        description=f"**{punishment['title']}** assigned to {submissive.mention}",
        color=discord.Color.purple()
    )
    embed.add_field(name="Description", value=punishment['description'], inline=False)
    embed.add_field(name="Assignment ID", value=str(assignment_id), inline=True)
    embed.add_field(name="Deadline", value=f"<t:{int(deadline.timestamp())}:R>", inline=True)
    embed.add_field(name="Point Penalty", value=f"{point_penalty} (doubles if late)", inline=True)
    if reason:
        embed.add_field(name="Reason", value=reason, inline=False)
    if forward_to:
        embed.add_field(name="📸 Image Forward", value=f"Proof will be sent to {forward_to.mention}", inline=False)
    
    await interaction.response.send_message(embed=embed)
    
    # Notify submissive
    try:
        notif = discord.Embed(
            title="🎲 Random Punishment Assigned",
            description=f"**{interaction.user.display_name}** rolled the dice and assigned you a punishment!",
            color=discord.Color.purple()
        )
        notif.add_field(name="Punishment", value=punishment['title'], inline=False)
        notif.add_field(name="Description", value=punishment['description'], inline=False)
        notif.add_field(name="Assignment ID", value=str(assignment_id), inline=True)
        notif.add_field(name="Deadline", value=f"<t:{int(deadline.timestamp())}:R>", inline=True)
        notif.add_field(name="Point Penalty", value=f"-{point_penalty} points (doubles to -{point_penalty * 2} if late!)", inline=False)
        if reason:
            notif.add_field(name="Reason", value=reason, inline=False)
        if forward_to:
            notif.add_field(name="📸 Image Forward", value=f"⚠️ Your proof will be sent to {forward_to.display_name}", inline=False)
        notif.set_footer(text=f"Submit proof with: /punishment_complete {assignment_id} proof:<image>")
        await submissive.send(embed=notif)
    except:
        pass

# ============ APPROVAL COMMANDS ============

@bot.tree.command(name="approve", description="Approve a pending task completion")
@app_commands.describe(completion_id="The completion ID to approve")
async def approve(interaction: discord.Interaction, completion_id: int):
    """Approve a task completion (dominant only)."""
    user = await db.get_user(interaction.user.id)
    if not user or user['role'] != 'dominant':
        await interaction.response.send_message(
            "❌ Only dominants can approve task completions!",
            ephemeral=True
        )
        return
    
    points = await db.approve_task_completion(completion_id, interaction.user.id, True)
    if points is None:
        await interaction.response.send_message(
            "❌ Completion not found or already reviewed!",
            ephemeral=True
        )
        return
    
    # Get completion details to notify submissive and check if task was late
    import aiosqlite
    async with aiosqlite.connect(db.DATABASE_NAME) as database:
        database.row_factory = aiosqlite.Row
        async with database.execute("""
            SELECT tc.submissive_id, tc.task_id, t.deadline, t.active
            FROM task_completions tc
            JOIN tasks t ON tc.task_id = t.id
            WHERE tc.id = ?
        """, (completion_id,)) as cursor:
            row = await cursor.fetchone()
            if row:
                submissive_id = row[0]
                task_id = row[1]
                deadline = row[2]
                was_late = row[3] == 0  # Task was deactivated due to missed deadline
                
                # Award points (double if it was late to refund the deduction)
                points_to_award = points * 2 if was_late else points
                
                # Get current user data to calculate old points
                user_data = await db.get_user(submissive_id)
                old_points = user_data['points'] if user_data else 0
                
                # Update points
                new_total = await db.update_points(submissive_id, points_to_award)
                
                description = f"Task completion #{completion_id} has been approved."
                if was_late:
                    description += "\n⚠️ **Late submission - Points refunded!**"
                
                embed = discord.Embed(
                    title="✅ Task Approved!",
                    description=description,
                    color=discord.Color.green()
                )
                embed.add_field(name="Points Awarded", value=str(points_to_award), inline=True)
                embed.add_field(name="Task ID", value=str(task_id), inline=True)
                if was_late:
                    embed.add_field(name="Note", value=f"Refunded {points} deducted points + {points} task points", inline=False)
                
                await interaction.response.send_message(embed=embed)
                
                # Post to approval channel if configured
                if config.APPROVAL_CHANNEL_NAME and interaction.guild:
                    await post_to_channel(interaction.guild, config.APPROVAL_CHANNEL_NAME, embed)
                
                # Check for newly affordable rewards
                affordable_rewards = await db.get_affordable_rewards(submissive_id, new_total)
                newly_affordable = [r for r in affordable_rewards if r['point_cost'] > old_points]
                
                # Notify submissive
                try:
                    sub_user = await bot.fetch_user(submissive_id)
                    notif_desc = f"Your task completion has been approved by {interaction.user.display_name}!"
                    if was_late:
                        notif_desc += "\n🎉 **Late penalty refunded!**"
                    
                    notif = discord.Embed(
                        title="🎉 Task Approved!",
                        description=notif_desc,
                        color=discord.Color.green()
                    )
                    notif.add_field(name="Points Earned", value=str(points_to_award), inline=True)
                    notif.add_field(name="Total Points", value=str(new_total), inline=True)
                    
                    # Add newly affordable rewards notification (show the most expensive newly unlocked)
                    if newly_affordable:
                        # Sort by cost descending and show the highest newly unlocked reward
                        most_valuable = sorted(newly_affordable, key=lambda r: r['point_cost'], reverse=True)[0]
                        notif.add_field(
                            name="🎉 New Reward Unlocked!",
                            value=f"✨ **{most_valuable['title']}**\n{most_valuable['description']}\n💰 **Cost:** {most_valuable['point_cost']} points",
                            inline=False
                        )
                        notif.set_footer(text="You've reached a new reward threshold!")
                    
                    await sub_user.send(embed=notif)
                except:
                    pass

@bot.tree.command(name="reject", description="Reject a pending task completion (deadline stays the same)")
@app_commands.describe(
    completion_id="The completion ID to reject",
    reason="Reason for rejection (optional)"
)
async def reject(interaction: discord.Interaction, completion_id: int, reason: str = None):
    """Reject a task completion - deadline remains the same (dominant only)."""
    user = await db.get_user(interaction.user.id)
    if not user or user['role'] != 'dominant':
        await interaction.response.send_message(
            "❌ Only dominants can reject task completions!",
            ephemeral=True
        )
        return
    
    points = await db.approve_task_completion(completion_id, interaction.user.id, False)
    if points is None:
        await interaction.response.send_message(
            "❌ Completion not found or already reviewed!",
            ephemeral=True
        )
        return
    
    # Get completion details to notify submissive
    import aiosqlite
    async with aiosqlite.connect(db.DATABASE_NAME) as database:
        database.row_factory = aiosqlite.Row
        async with database.execute(
            "SELECT submissive_id, task_id FROM task_completions WHERE id = ?",
            (completion_id,)
        ) as cursor:
            row = await cursor.fetchone()
            if row:
                submissive_id = row[0]
                task_id = row[1]
                
                embed = discord.Embed(
                    title="❌ Task Rejected",
                    description=f"Task completion #{completion_id} has been rejected.\n⏰ **Deadline remains the same.**",
                    color=discord.Color.red()
                )
                embed.add_field(name="Task ID", value=str(task_id), inline=True)
                if reason:
                    embed.add_field(name="Reason", value=reason, inline=False)
                
                await interaction.response.send_message(embed=embed)
                
                # Post to approval channel if configured
                if config.APPROVAL_CHANNEL_NAME and interaction.guild:
                    await post_to_channel(interaction.guild, config.APPROVAL_CHANNEL_NAME, embed)
                
                # Notify submissive
                try:
                    sub_user = await bot.fetch_user(submissive_id)
                    notif = discord.Embed(
                        title="❌ Task Rejected",
                        description=f"Your task completion was rejected by {interaction.user.display_name}.",
                        color=discord.Color.red()
                    )
                    notif.add_field(name="Task ID", value=str(task_id), inline=True)
                    if reason:
                        notif.add_field(name="Reason", value=reason, inline=False)
                    notif.set_footer(text="⏰ Deadline remains the same. Submit again!")
                    await sub_user.send(embed=notif)
                except:
                    pass

@bot.tree.command(name="reject_cancel", description="Reject task and reset deadline to next occurrence")
@app_commands.describe(
    completion_id="The completion ID to reject",
    reason="Reason for cancellation (optional)"
)
async def reject_cancel(interaction: discord.Interaction, completion_id: int, reason: str = None):
    """Reject task completion and reset deadline to next occurrence (dominant only)."""
    user = await db.get_user(interaction.user.id)
    if not user or user['role'] != 'dominant':
        await interaction.response.send_message(
            "❌ Only dominants can reject task completions!",
            ephemeral=True
        )
        return
    
    # Reject and reset deadline
    points = await db.approve_task_completion(completion_id, interaction.user.id, False, reset_deadline_on_reject=True)
    if points is None:
        await interaction.response.send_message(
            "❌ Completion not found or already reviewed!",
            ephemeral=True
        )
        return
    
    # Get completion details to notify submissive
    import aiosqlite
    async with aiosqlite.connect(db.DATABASE_NAME) as database:
        database.row_factory = aiosqlite.Row
        async with database.execute(
            "SELECT submissive_id, task_id FROM task_completions WHERE id = ?",
            (completion_id,)
        ) as cursor:
            row = await cursor.fetchone()
            if row:
                submissive_id = row[0]
                task_id = row[1]
                
                embed = discord.Embed(
                    title="❌ Task Rejected & Reset",
                    description=f"Task completion #{completion_id} rejected.\n🔄 **Deadline reset to next occurrence.**",
                    color=discord.Color.orange()
                )
                embed.add_field(name="Task ID", value=str(task_id), inline=True)
                if reason:
                    embed.add_field(name="Reason", value=reason, inline=False)
                
                await interaction.response.send_message(embed=embed)
                
                # Post to approval channel if configured
                if config.APPROVAL_CHANNEL_NAME and interaction.guild:
                    await post_to_channel(interaction.guild, config.APPROVAL_CHANNEL_NAME, embed)
                
                # Notify submissive
                try:
                    sub_user = await bot.fetch_user(submissive_id)
                    notif = discord.Embed(
                        title="❌ Task Rejected & Reset",
                        description=f"Your task was rejected by {interaction.user.display_name}.",
                        color=discord.Color.orange()
                    )
                    notif.add_field(name="Task ID", value=str(task_id), inline=True)
                    if reason:
                        notif.add_field(name="Reason", value=reason, inline=False)
                    notif.set_footer(text="🔄 Deadline has been reset to next occurrence.")
                    await sub_user.send(embed=notif)
                except:
                    pass

@bot.tree.command(name="verify", description="Manually verify a task without proof (dominant override)")
@app_commands.describe(
    submissive="The submissive who completed the task",
    task_id="The task ID to verify"
)
async def verify(interaction: discord.Interaction, submissive: discord.Member, task_id: int):
    """Manually verify task completion without proof (dominant only)."""
    user = await db.get_user(interaction.user.id)
    if not user or user['role'] != 'dominant':
        await interaction.response.send_message(
            "❌ Only dominants can verify tasks!",
            ephemeral=True
        )
        return
    
    # Submit and immediately approve
    completion_id = await db.submit_task_completion(task_id, submissive.id, None)
    if completion_id is None:
        await interaction.response.send_message(
            "❌ Task not found!",
            ephemeral=True
        )
        return
    
    points = await db.approve_task_completion(completion_id, interaction.user.id, True)
    if points:
        new_total = await db.update_points(submissive.id, points)
        
        embed = discord.Embed(
            title="✅ Task Verified",
            description=f"Task manually verified for {submissive.mention}",
            color=discord.Color.green()
        )
        embed.add_field(name="Points Awarded", value=str(points), inline=True)
        embed.add_field(name="New Total", value=str(new_total), inline=True)
        
        await interaction.response.send_message(embed=embed)
        
        # Notify submissive
        try:
            notif = discord.Embed(
                title="✅ Task Verified",
                description=f"**{interaction.user.display_name}** verified your task completion!",
                color=discord.Color.green()
            )
            notif.add_field(name="Points Earned", value=str(points), inline=True)
            notif.add_field(name="Total Points", value=str(new_total), inline=True)
            await submissive.send(embed=notif)
        except:
            pass

@bot.tree.command(name="pending", description="View pending task completions")
async def pending(interaction: discord.Interaction):
    """View pending task completions (dominant only)."""
    user = await db.get_user(interaction.user.id)
    if not user or user['role'] != 'dominant':
        await interaction.response.send_message(
            "❌ Only dominants can view pending completions!",
            ephemeral=True
        )
        return
    
    pending_list = await db.get_pending_completions(interaction.user.id)
    
    if not pending_list:
        await interaction.response.send_message(
            "✅ No pending task completions!",
            ephemeral=True
        )
        return
    
    embed = discord.Embed(
        title="📋 Pending Task Completions",
        description=f"{len(pending_list)} task(s) awaiting review",
        color=discord.Color.orange()
    )
    
    for item in pending_list[:10]:  # Show max 10
        value = f"**Submissive:** {item['submissive_name']}\n**Task:** {item['title']}\n**Submitted:** <t:{int(datetime.datetime.fromisoformat(item['submitted_at']).timestamp())}:R>"
        if item['proof_url']:
            value += f"\n[View Proof]({item['proof_url']})"
        embed.add_field(
            name=f"Completion ID: {item['id']}",
            value=value,
            inline=False
        )
    
    embed.set_footer(text="Use /approve <id> or /reject <id> to review")
    await interaction.response.send_message(embed=embed)

# ============ POINTS AND STATS COMMANDS ============

@bot.tree.command(name="points", description="Check your points or a submissive's points")
@app_commands.describe(submissive="Check points for this submissive (dominants only)")
async def points(interaction: discord.Interaction, submissive: discord.Member = None):
    """Check points."""
    user = await db.get_user(interaction.user.id)
    if not user:
        await interaction.response.send_message(
            "❌ You need to register first! Use `/register`",
            ephemeral=True
        )
        return
    
    # Determine whose points to show
    if submissive:
        if user['role'] != 'dominant':
            await interaction.response.send_message(
                "❌ Only dominants can view others' points!",
                ephemeral=True
            )
            return
        target = await db.get_user(submissive.id)
        target_name = submissive.display_name
    else:
        target = user
        target_name = "You"
    
    if not target:
        await interaction.response.send_message(
            "❌ User not registered!",
            ephemeral=True
        )
        return
    
    embed = discord.Embed(
        title="💸 Points Balance",
        description=f"{target_name} {'have' if target_name == 'You' else 'has'} **{target['points']}** points",
        color=discord.Color.purple()
    )
    
    # If submissive checking their own points, show affordable rewards
    if target_name == "You" and user['role'] == 'submissive':
        affordable_rewards = await db.get_affordable_rewards(interaction.user.id, target['points'])
        if affordable_rewards:
            rewards_text = "\n".join([f"✨ **{r['title']}** - {r['point_cost']} points" for r in affordable_rewards[:5]])
            embed.add_field(name="🎁 Rewards You Can Afford", value=rewards_text, inline=False)
        else:
            embed.add_field(name="🎁 Rewards", value="Keep earning points to unlock rewards!", inline=False)
    
    await interaction.response.send_message(embed=embed)

@bot.tree.command(name="stats", description="View task completion statistics")
@app_commands.describe(
    submissive="View stats for this submissive (dominants only)",
    days="Number of days to show (default: 7)"
)
async def stats(interaction: discord.Interaction, submissive: discord.Member = None, days: int = 7):
    """View statistics."""
    user = await db.get_user(interaction.user.id)
    if not user:
        await interaction.response.send_message(
            "❌ You need to register first! Use `/register`",
            ephemeral=True
        )
        return
    
    # Determine whose stats to show
    if submissive:
        if user['role'] != 'dominant':
            await interaction.response.send_message(
                "❌ Only dominants can view others' stats!",
                ephemeral=True
            )
            return
        target_id = submissive.id
        target_name = submissive.display_name
    else:
        if user['role'] == 'dominant':
            await interaction.response.send_message(
                "❌ Specify a submissive to view their stats!",
                ephemeral=True
            )
            return
        target_id = interaction.user.id
        target_name = "Your"
    
    stats_data = await db.get_task_stats(target_id, days)
    
    embed = discord.Embed(
        title=f"📊 {target_name} Stats (Last {days} Days)",
        color=discord.Color.blue()
    )
    embed.add_field(name="Total Completions", value=str(stats_data['total_completions']), inline=True)
    embed.add_field(name="Total Points Earned", value=str(stats_data['total_points']), inline=True)
    
    # Create graph if there's data
    if stats_data['daily_stats']:
        dates = [s['date'] for s in stats_data['daily_stats']]
        counts = [s['count'] for s in stats_data['daily_stats']]
        
        plt.figure(figsize=(10, 5))
        plt.bar(dates, counts, color='#5865F2')
        plt.xlabel('Date')
        plt.ylabel('Tasks Completed')
        plt.title(f'{target_name} Task Completion')
        plt.xticks(rotation=45)
        plt.tight_layout()
        
        # Save to buffer
        buf = io.BytesIO()
        plt.savefig(buf, format='png')
        buf.seek(0)
        plt.close()
        
        file = discord.File(buf, filename='stats.png')
        embed.set_image(url='attachment://stats.png')
        await interaction.response.send_message(embed=embed, file=file)
    else:
        await interaction.response.send_message(embed=embed)

# ============ UTILITY COMMANDS ============

@bot.tree.command(name="timezone", description="Set your timezone for deadline calculations")
@app_commands.describe(
    timezone="Timezone (e.g., EST, CST, PST, GMT, UTC)"
)
async def timezone(interaction: discord.Interaction, timezone: str = None):
    """Set or view user's timezone."""
    user = await db.get_user(interaction.user.id)
    if not user:
        await interaction.response.send_message(
            "❌ You need to register first! Use `/register`",
            ephemeral=True
        )
        return
    
    if timezone is None:
        # Show current timezone
        current_tz = await db.get_user_timezone(interaction.user.id)
        tz = pytz.timezone(current_tz)
        now = datetime.datetime.now(tz)
        
        embed = discord.Embed(
            title="⏰ Your Timezone Settings",
            color=discord.Color.blue()
        )
        embed.add_field(name="Current Timezone", value=current_tz, inline=False)
        embed.add_field(name="Your Current Time", value=now.strftime("%Y-%m-%d %H:%M:%S"), inline=False)
        embed.set_footer(text="Change with: /timezone timezone:<your_timezone>\nExamples: EST, CST, PST, GMT, UTC")
        await interaction.response.send_message(embed=embed, ephemeral=True)
    else:
        # Map common abbreviations to IANA timezone names
        tz_map = {
            # US Timezones
            'EST': 'America/New_York',
            'EDT': 'America/New_York',
            'ET': 'America/New_York',
            'CST': 'America/Chicago',
            'CDT': 'America/Chicago',
            'CT': 'America/Chicago',
            'MST': 'America/Denver',
            'MDT': 'America/Denver',
            'MT': 'America/Denver',
            'PST': 'America/Los_Angeles',
            'PDT': 'America/Los_Angeles',
            'PT': 'America/Los_Angeles',
            # Europe
            'GMT': 'Europe/London',
            'BST': 'Europe/London',
            'CET': 'Europe/Paris',
            'CEST': 'Europe/Paris',
            # Asia
            'JST': 'Asia/Tokyo',
            'KST': 'Asia/Seoul',
            'CST_CHINA': 'Asia/Shanghai',
            # Australia
            'AEST': 'Australia/Sydney',
            'AEDT': 'Australia/Sydney',
            # Universal
            'UTC': 'UTC',
        }
        
        # Convert to uppercase for case-insensitive matching
        tz_upper = timezone.upper()
        tz_to_use = tz_map.get(tz_upper, timezone)
        
        # Set new timezone
        success = await db.set_user_timezone(interaction.user.id, tz_to_use)
        if success:
            tz = pytz.timezone(tz_to_use)
            now = datetime.datetime.now(tz)
            
            display_name = timezone if tz_upper in tz_map else tz_to_use
            
            embed = discord.Embed(
                title="✅ Timezone Updated",
                description=f"Your timezone has been set to **{display_name}**",
                color=discord.Color.green()
            )
            embed.add_field(name="IANA Name", value=tz_to_use, inline=False)
            embed.add_field(name="Your Current Time", value=now.strftime("%Y-%m-%d %H:%M:%S"), inline=False)
            embed.set_footer(text="All deadlines will now be calculated in your timezone")
            await interaction.response.send_message(embed=embed, ephemeral=True)
        else:
            await interaction.response.send_message(
                f"❌ Invalid timezone: '{timezone}'\n\nSupported abbreviations:\n• EST/ET (East Coast US)\n• CST/CT (Central US)\n• MST/MT (Mountain US)\n• PST/PT (West Coast US)\n• GMT (UK)\n• CET (Central Europe)\n• JST (Japan)\n• UTC (Universal)\n\nOr use IANA format: America/New_York, Europe/London, etc.",
                ephemeral=True
            )

@bot.tree.command(name="help", description="Show all available commands")
async def help_command(interaction: discord.Interaction):
    """Show help."""
    embed = discord.Embed(
        title="🤖 Obedience Bot Commands",
        description="A BDSM-themed habit tracker bot",
        color=discord.Color.blurple()
    )
    
    embed.add_field(
        name="📝 Registration",
        value="`/register` - Register as dominant or submissive\n`/link` - Link a dominant with a submissive",
        inline=False
    )
    
    embed.add_field(
        name="📋 Tasks",
        value="`/task_add` - Add a new task (supports specific deadlines & auto-punish)\n`/tasks` - View tasks\n`/task_complete` - Submit task with proof\n`/task_edit` - Edit existing task (dom)\n`/task_delete` - Delete task (dom)\n`/verify` - Manually verify task (dom)",
        inline=False
    )
    
    embed.add_field(
        name="✅ Approvals (Dominant Only)",
        value="`/pending` - View pending completions\n`/approve` - Approve a completion\n`/reject` - Reject a completion",
        inline=False
    )
    
    embed.add_field(
        name="🎁 Rewards",
        value="`/reward_create` - Create a reward\n`/rewards` - View rewards\n`/reward_assign` - Give a reward\n`/reward_edit` - Edit reward (dom)\n`/reward_delete` - Delete reward (dom)",
        inline=False
    )
    
    embed.add_field(
        name="⚠️ Punishments",
        value="`/punishment_create` - Create a punishment\n`/punishments` - View punishments\n`/punishment_assign` - Assign with specific deadline\n`/punishment_assign_random` - Assign random with deadline\n`/punishment_edit` - Edit punishment (dom)\n`/punishment_delete` - Delete punishment (dom)",
        inline=False
    )
    
    embed.add_field(
        name="📊 Stats & Points",
        value="`/points` - Check points balance\n`/stats` - View completion statistics",
        inline=False
    )
    
    embed.add_field(
        name="⏰ Settings",
        value="`/timezone` - Set your timezone for deadline calculations",
        inline=False
    )
    
    await interaction.response.send_message(embed=embed)

# Run the bot
if __name__ == "__main__":
    bot.run(TOKEN)
