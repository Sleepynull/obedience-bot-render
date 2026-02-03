import discord
from discord.ext import commands
from discord import app_commands
import os
from dotenv import load_dotenv
import database as db
import io
import matplotlib
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

@bot.event
async def on_ready():
    """Initialize bot when ready."""
    await db.init_db()
    try:
        synced = await bot.tree.sync()
        print(f"Synced {len(synced)} command(s)")
    except Exception as e:
        print(f"Failed to sync commands: {e}")
    print(f'{bot.user} is now online!')

# ============ REGISTRATION COMMANDS ============

@bot.tree.command(name="register", description="Register as a dominant or submissive")
@app_commands.describe(role="Your role: dominant or submissive")
@app_commands.choices(role=[
    app_commands.Choice(name="Dominant", value="dominant"),
    app_commands.Choice(name="Submissive", value="submissive")
])
async def register(interaction: discord.Interaction, role: app_commands.Choice[str]):
    """Register a user with their role."""
    success = await db.register_user(interaction.user.id, str(interaction.user), role.value)
    if success:
        await interaction.response.send_message(
            f"✅ You've been registered as a **{role.value}**!",
            ephemeral=True
        )
    else:
        await interaction.response.send_message(
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
    frequency="How often: daily or weekly",
    points="Points earned on completion (default: 10)"
)
@app_commands.choices(frequency=[
    app_commands.Choice(name="Daily", value="daily"),
    app_commands.Choice(name="Weekly", value="weekly")
])
async def task_add(
    interaction: discord.Interaction,
    submissive: discord.Member,
    title: str,
    description: str,
    frequency: app_commands.Choice[str],
    points: int = 10
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
    
    # Create task
    task_id = await db.create_task(
        submissive.id,
        interaction.user.id,
        title,
        description,
        frequency.value,
        points
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
    embed.set_footer(text=f"Task ID: {task_id}")
    
    await interaction.response.send_message(embed=embed)
    
    # Notify submissive
    try:
        await submissive.send(f"📋 **New task assigned by {interaction.user.display_name}!**\n\n**{title}**\n{description}\n\nFrequency: {frequency.value} | Points: {points}")
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
        embed.add_field(
            name=f"{task['id']}. {task['title']}",
            value=value,
            inline=False
        )
    
    await interaction.response.send_message(embed=embed)

@bot.tree.command(name="task_complete", description="Mark a task as completed")
@app_commands.describe(task_id="The ID of the task to complete")
async def task_complete(interaction: discord.Interaction, task_id: int):
    """Complete a task (submissive only)."""
    user = await db.get_user(interaction.user.id)
    if not user or user['role'] != 'submissive':
        await interaction.response.send_message(
            "❌ Only submissives can complete tasks!",
            ephemeral=True
        )
        return
    
    points_earned = await db.complete_task(task_id, interaction.user.id)
    if points_earned is None:
        await interaction.response.send_message(
            "❌ Task not found or already completed!",
            ephemeral=True
        )
        return
    
    # Update points
    new_total = await db.update_points(interaction.user.id, points_earned)
    
    embed = discord.Embed(
        title="✅ Task Completed!",
        description=f"Great work! You earned **{points_earned}** points!",
        color=discord.Color.green()
    )
    embed.add_field(name="Total Points", value=str(new_total))
    
    await interaction.response.send_message(embed=embed)
    
    # Notify dominant
    dominant = await db.get_dominant(interaction.user.id)
    if dominant:
        try:
            dom_user = await bot.fetch_user(dominant['user_id'])
            await dom_user.send(
                f"✅ **{interaction.user.display_name}** completed task #{task_id} and earned {points_earned} points!"
            )
        except:
            pass

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
    
    # Get dominant ID
    if user['role'] == 'dominant':
        dominant_id = interaction.user.id
    else:
        dominant = await db.get_dominant(interaction.user.id)
        if not dominant:
            await interaction.response.send_message(
                "❌ You're not linked to a dominant!",
                ephemeral=True
            )
            return
        dominant_id = dominant['user_id']
    
    rewards_list = await db.get_rewards(dominant_id)
    
    if not rewards_list:
        await interaction.response.send_message(
            "No rewards available yet!",
            ephemeral=True
        )
        return
    
    embed = discord.Embed(
        title="🎁 Available Rewards",
        color=discord.Color.gold()
    )
    
    for reward in rewards_list:
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
    """Assign a reward (dominant only)."""
    user = await db.get_user(interaction.user.id)
    if not user or user['role'] != 'dominant':
        await interaction.response.send_message(
            "❌ Only dominants can assign rewards!",
            ephemeral=True
        )
        return
    
    await db.assign_reward(submissive.id, interaction.user.id, reward_id, reason)
    
    await interaction.response.send_message(
        f"🎁 Reward assigned to {submissive.mention}!"
    )
    
    # Notify submissive
    try:
        msg = f"🎁 **You've been given a reward by {interaction.user.display_name}!**"
        if reason:
            msg += f"\nReason: {reason}"
        await submissive.send(msg)
    except:
        pass

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
    
    # Get dominant ID
    if user['role'] == 'dominant':
        dominant_id = interaction.user.id
    else:
        dominant = await db.get_dominant(interaction.user.id)
        if not dominant:
            await interaction.response.send_message(
                "❌ You're not linked to a dominant!",
                ephemeral=True
            )
            return
        dominant_id = dominant['user_id']
    
    punishments_list = await db.get_punishments(dominant_id)
    
    if not punishments_list:
        await interaction.response.send_message(
            "No punishments available yet!",
            ephemeral=True
        )
        return
    
    embed = discord.Embed(
        title="⚠️ Available Punishments",
        color=discord.Color.red()
    )
    
    for punishment in punishments_list:
        embed.add_field(
            name=f"{punishment['id']}. {punishment['title']}",
            value=punishment['description'],
            inline=False
        )
    
    await interaction.response.send_message(embed=embed)

@bot.tree.command(name="punishment_assign", description="Assign a punishment to a submissive")
@app_commands.describe(
    submissive="The submissive to punish",
    punishment_id="The punishment ID",
    reason="Reason for the punishment (optional)"
)
async def punishment_assign(
    interaction: discord.Interaction,
    submissive: discord.Member,
    punishment_id: int,
    reason: str = None
):
    """Assign a punishment (dominant only)."""
    user = await db.get_user(interaction.user.id)
    if not user or user['role'] != 'dominant':
        await interaction.response.send_message(
            "❌ Only dominants can assign punishments!",
            ephemeral=True
        )
        return
    
    await db.assign_punishment(submissive.id, interaction.user.id, punishment_id, reason)
    
    await interaction.response.send_message(
        f"⚠️ Punishment assigned to {submissive.mention}!"
    )
    
    # Notify submissive
    try:
        msg = f"⚠️ **You've been given a punishment by {interaction.user.display_name}!**"
        if reason:
            msg += f"\nReason: {reason}"
        await submissive.send(msg)
    except:
        pass

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
        title="💎 Points Balance",
        description=f"{target_name} {'have' if target_name == 'You' else 'has'} **{target['points']}** points",
        color=discord.Color.purple()
    )
    
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
        value="`/task_add` - Add a new task\n`/tasks` - View tasks\n`/task_complete` - Complete a task",
        inline=False
    )
    
    embed.add_field(
        name="🎁 Rewards",
        value="`/reward_create` - Create a reward\n`/rewards` - View rewards\n`/reward_assign` - Give a reward",
        inline=False
    )
    
    embed.add_field(
        name="⚠️ Punishments",
        value="`/punishment_create` - Create a punishment\n`/punishments` - View punishments\n`/punishment_assign` - Give a punishment",
        inline=False
    )
    
    embed.add_field(
        name="📊 Stats & Points",
        value="`/points` - Check points balance\n`/stats` - View completion statistics",
        inline=False
    )
    
    await interaction.response.send_message(embed=embed)

# Run the bot
if __name__ == "__main__":
    bot.run(TOKEN)
