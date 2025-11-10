import discord
from discord.ext import commands
from discord import app_commands
import os
import datetime
import asyncio
from flask import Flask
from threading import Thread

# -----------------------------
# Flask Keep-Alive (Render)
# -----------------------------
app = Flask(__name__)

@app.route('/')
def home():
    return "RASH TECH Bot is running!"

def run_flask():
    app.run(host="0.0.0.0", port=8080)

Thread(target=run_flask).start()

# -----------------------------
# Discord Bot Setup
# -----------------------------
intents = discord.Intents.default()
intents.message_content = True
intents.members = True

bot = commands.Bot(command_prefix="!", intents=intents)
bot.remove_command("help")

# Environment Variables
DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")
GUILD_ID = int(os.getenv("GUILD_ID"))
TICKET_LOG_CHANNEL_ID = int(os.getenv("TICKET_LOG_CHANNEL_ID"))
YOUTUBE_CHANNEL_URL = os.getenv("YOUTUBE_CHANNEL_URL")

# Hardcoded Channels
TICKET_COUNTER_CHANNEL_ID = 1431633723467501769
VERIFICATION_CHANNEL_ID = 1437035128802246697

# Data stores
user_cooldowns = {}   # {user_id: datetime}
apps = {}             # {app_name: link}
active_tickets = {}   # {user_id: channel_id}


# -----------------------------
# Helper Embed Function
# -----------------------------
def create_embed(title, desc, color=discord.Color.blurple()):
    embed = discord.Embed(title=title, description=desc, color=color)
    embed.set_footer(text="RASH TECH | Premium App Service ⚡")
    return embed


# -----------------------------
# Dynamic App Management
# -----------------------------
@bot.tree.command(name="addapp", description="➕ Add a premium app with its link")
@app_commands.checks.has_permissions(manage_guild=True)
@app_commands.describe(name="App name", link="App link")
async def addapp(interaction: discord.Interaction, name: str, link: str):
    name = name.lower()
    if name in apps:
        await interaction.response.send_message(
            f"⚠️ The app **{name.title()}** already exists.", ephemeral=True
        )
        return
    apps[name] = link
    await interaction.response.send_message(
        f"✅ **{name.title()}** added successfully with link:\n{link}", ephemeral=True
    )


@bot.tree.command(name="removeapp", description="❌ Remove an app from the premium list")
@app_commands.checks.has_permissions(manage_guild=True)
@app_commands.describe(name="App name")
async def removeapp(interaction: discord.Interaction, name: str):
    name = name.lower()
    if name not in apps:
        await interaction.response.send_message(
            f"⚠️ No app named **{name.title()}** found.", ephemeral=True
        )
        return
    del apps[name]
    await interaction.response.send_message(
        f"🗑️ **{name.title()}** has been removed from the list.", ephemeral=True
    )


@bot.tree.command(name="listapps", description="📜 View all currently available premium apps")
async def listapps(interaction: discord.Interaction):
    if not apps:
        await interaction.response.send_message(
            embed=create_embed("📭 No Apps Found", "There are currently no premium apps."),
            ephemeral=True,
        )
        return

    embed = discord.Embed(
        title="💎 Premium Apps List",
        description="Here are all the premium apps currently available:",
        color=discord.Color.green(),
    )
    for app_name, app_link in sorted(apps.items()):
        embed.add_field(name=app_name.title(), value=f"[🔗 Click Here]({app_link})", inline=False)

    embed.set_footer(text="RASH TECH | More apps coming soon ⚡")
    await interaction.response.send_message(embed=embed)


# -----------------------------
# Ticket Command
# -----------------------------
@bot.tree.command(name="ticket", description="🎟️ Create a support ticket")
async def ticket(interaction: discord.Interaction):
    user = interaction.user
    guild = interaction.guild
    now = datetime.datetime.utcnow()

    if user.id in user_cooldowns and now - user_cooldowns[user.id] < datetime.timedelta(hours=48):
        remaining = datetime.timedelta(hours=48) - (now - user_cooldowns[user.id])
        await interaction.response.send_message(
            f"⏳ You can create another ticket in **{remaining.seconds // 3600}h {(remaining.seconds // 60) % 60}m**.",
            ephemeral=True,
        )
        return

    overwrites = {
        guild.default_role: discord.PermissionOverwrite(view_channel=False),
        user: discord.PermissionOverwrite(view_channel=True, send_messages=True, attach_files=True),
        guild.me: discord.PermissionOverwrite(view_channel=True)
    }

    ticket_channel = await guild.create_text_channel(
        f"ticket-{user.name}".replace(" ", "-"),
        overwrites=overwrites,
        reason=f"Ticket created by {user}"
    )

    user_cooldowns[user.id] = now
    active_tickets[user.id] = ticket_channel.id

    app_list_text = "\n".join([f"💠 **{a.title()}**" for a in apps.keys()]) if apps else "No apps available yet."

    embed = discord.Embed(
        title=f"🎫 Welcome to RASH TECH, {user.display_name}!",
        description=(
            "Thank you for reaching out to **RASH TECH Support** 💬\n\n"
            "Please follow these steps to get your premium app link:\n"
            "1️⃣ Go to our YouTube channel and **Subscribe**: "
            f"[RASH TECH]({YOUTUBE_CHANNEL_URL})\n"
            "2️⃣ Take a **screenshot** of your subscription.\n"
            "3️⃣ Upload the screenshot **here in this ticket**.\n\n"
            "Once verified by admin, you’ll receive your app link directly in DM. 💎\n\n"
            f"**Available Premium Apps:**\n{app_list_text}"
        ),
        color=discord.Color.green()
    )

    await ticket_channel.send(embed=embed)
    await interaction.response.send_message(
        f"✅ Your ticket has been created: {ticket_channel.mention}", ephemeral=True
    )


# -----------------------------
# Handle Screenshot Upload
# -----------------------------
@bot.event
async def on_message(message):
    if message.author.bot:
        return

    if message.channel.id not in active_tickets.values():
        return

    user = message.author
    guild = message.guild
    channel = message.channel

    # If the message contains an attachment (screenshot)
    if message.attachments:
        verification_channel = guild.get_channel(VERIFICATION_CHANNEL_ID)
        if not verification_channel:
            await channel.send("⚠️ Verification channel not found. Please contact admin.")
            return

        last_user_message = None
        async for msg in channel.history(limit=10):
            if msg.author == user and not msg.attachments:
                last_user_message = msg.content.lower().strip()
                break

        app_name = last_user_message.lower() if last_user_message else None
        if app_name not in apps:
            await channel.send(embed=create_embed(
                "⚠️ Invalid App Name",
                "Please type the app name (e.g., Spotify, Youtube) before sending your screenshot.",
                discord.Color.red()
            ))
            return

        file = await message.attachments[0].to_file()
        embed = discord.Embed(
            title="🧾 New Verification Request",
            description=f"👤 **User:** {user.mention}\n📱 **App:** {app_name.title()}",
            color=discord.Color.orange()
        )
        embed.set_image(url=message.attachments[0].url)

        verify_btn = discord.ui.Button(label="✅ Verify", style=discord.ButtonStyle.success)
        decline_btn = discord.ui.Button(label="❌ Decline", style=discord.ButtonStyle.danger)
        view = discord.ui.View()

        async def verify_callback(interaction_btn: discord.Interaction):
            await interaction_btn.response.send_message(
                f"✅ Verified **{user.display_name}** for **{app_name.title()}**.", ephemeral=False
            )
            await channel.send(embed=create_embed(
                "✅ Verification Approved",
                "Your verification has been approved! Check your DMs for the app link 💎",
                discord.Color.green())
            )
            try:
                await user.send(f"🎉 Here is your **{app_name.title()}** link: {apps[app_name]}")
            except:
                await channel.send("⚠️ Unable to send DM. Please check your privacy settings.")

        async def decline_callback(interaction_btn: discord.Interaction):
            await interaction_btn.response.send_message(
                f"❌ Verification declined for **{user.display_name}**.", ephemeral=False
            )
            await channel.send(embed=create_embed(
                "❌ Verification Declined",
                "Your screenshot was declined by the admin. Please try again.",
                discord.Color.red())
            )

        verify_btn.callback = verify_callback
        decline_btn.callback = decline_callback
        view.add_item(verify_btn)
        view.add_item(decline_btn)

        await verification_channel.send(embed=embed, view=view)
        await channel.send(embed=create_embed(
            "📸 Upload Successful",
            "Please wait while the admin verifies your screenshot."
        ))


# -----------------------------
# Admin Commands
# -----------------------------
@bot.tree.command(name="remove_cooldown", description="🧹 Remove a user's ticket cooldown")
@app_commands.checks.has_permissions(manage_channels=True)
@app_commands.describe(user="User to remove cooldown for")
async def remove_cooldown(interaction: discord.Interaction, user: discord.Member):
    if user.id in user_cooldowns:
        del user_cooldowns[user.id]
        await interaction.response.send_message(f"✅ Cooldown removed for {user.mention}", ephemeral=True)
    else:
        await interaction.response.send_message(f"⚠️ {user.mention} has no active cooldown.", ephemeral=True)


@bot.tree.command(name="force_close", description="🔒 Force close a user's ticket")
@app_commands.checks.has_permissions(manage_channels=True)
@app_commands.describe(user="User whose ticket you want to close")
async def force_close(interaction: discord.Interaction, user: discord.Member):
    if user.id not in active_tickets:
        await interaction.response.send_message("⚠️ No active ticket found for that user.", ephemeral=True)
        return

    channel_id = active_tickets[user.id]
    channel = bot.get_channel(channel_id)
    if channel:
        await channel.delete(reason="Force closed by admin")
        del active_tickets[user.id]
        await interaction.response.send_message(f"✅ Ticket closed for {user.mention}", ephemeral=True)


# -----------------------------
# On Ready
# -----------------------------
@bot.event
async def on_ready():
    await bot.tree.sync(guild=discord.Object(id=GUILD_ID))
    print(f"✅ Logged in as {bot.user}")


# -----------------------------
# Run Bot
# -----------------------------
bot.run(DISCORD_TOKEN)
