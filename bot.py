import discord
from discord.ext import commands
from discord import app_commands
import os, json, datetime
from flask import Flask
from threading import Thread

# ---------------------------
# Environment Variables
# ---------------------------
TOKEN = os.getenv("DISCORD_TOKEN")
GUILD_ID = int(os.getenv("GUILD_ID"))
TICKET_LOG_CHANNEL_ID = int(os.getenv("TICKET_LOG_CHANNEL_ID"))
YOUTUBE_CHANNEL_URL = os.getenv("YOUTUBE_CHANNEL_URL")

# ---------------------------
# Bot Setup
# ---------------------------
intents = discord.Intents.default()
intents.message_content = True
intents.members = True
bot = commands.Bot(command_prefix="/", intents=intents)
GUILD = discord.Object(id=GUILD_ID)

user_cooldowns = {}

def load_apps():
    with open("apps.json", "r") as f:
        return json.load(f)

apps = load_apps()

# ---------------------------
# Flask Keep Alive
# ---------------------------
app = Flask("")

@app.route("/")
def home():
    return "Bot is running! ✅"

def run():
    app.run(host="0.0.0.0", port=8080)

Thread(target=run).start()

# ---------------------------
# Views & Buttons
# ---------------------------
class TicketView(discord.ui.View):
    def __init__(self, user):
        super().__init__(timeout=None)
        self.user = user

    @discord.ui.button(label="🎫 Create Ticket", style=discord.ButtonStyle.green, emoji="🎫", custom_id="create_ticket")
    async def create_ticket(self, interaction: discord.Interaction, button: discord.ui.Button):
        if self.user:
            now = datetime.datetime.utcnow()
            if self.user.id in user_cooldowns:
                last = user_cooldowns[self.user.id]
                if (now - last).total_seconds() < 48*3600:
                    await interaction.response.send_message(
                        "⏳ You can only create a ticket every 48 hours.", ephemeral=True
                    )
                    return
            user_cooldowns[self.user.id] = now
            guild = interaction.guild
        else:
            self.user = interaction.user
            guild = interaction.guild
            now = datetime.datetime.utcnow()
            user_cooldowns[self.user.id] = now

        overwrites = {
            guild.default_role: discord.PermissionOverwrite(read_messages=False),
            self.user: discord.PermissionOverwrite(read_messages=True, send_messages=True)
        }
        staff_role = discord.utils.get(guild.roles, name="Staff")
        if staff_role:
            overwrites[staff_role] = discord.PermissionOverwrite(read_messages=True, send_messages=True)

        channel = await guild.create_text_channel(
            name=f"ticket-{self.user.name}", overwrites=overwrites
        )

        embed = discord.Embed(
            title="🎟️ Support Ticket Created!",
            description=f"Hello {self.user.mention}!\n\nPlease describe your issue or type the name of the premium app you need.",
            color=discord.Color.blurple()
        )
        embed.set_footer(text="Staff will assist you shortly ✅")
        embed.set_thumbnail(url="https://i.imgur.com/7ZQv1Qz.png")
        await channel.send(embed=embed, view=TicketCloseView(channel))
        await interaction.response.send_message(f"✅ Your ticket has been created: {channel.mention}", ephemeral=True)

class TicketCloseView(discord.ui.View):
    def __init__(self, channel):
        super().__init__(timeout=None)
        self.channel = channel

    @discord.ui.button(label="🔒 Close Ticket", style=discord.ButtonStyle.red, emoji="🔒")
    async def close_ticket(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_message("⚠️ Are you sure you want to close this ticket?", ephemeral=True)
        await interaction.followup.send(embed=discord.Embed(
            title="❗ Confirm Close",
            description="Click the button below to permanently close this ticket.",
            color=discord.Color.red()
        ), view=ConfirmCloseView(self.channel))

class ConfirmCloseView(discord.ui.View):
    def __init__(self, channel):
        super().__init__(timeout=None)
        self.channel = channel

    @discord.ui.button(label="✅ Confirm Close", style=discord.ButtonStyle.green, emoji="✅")
    async def confirm(self, interaction: discord.Interaction, button: discord.ui.Button):
        messages = [msg async for msg in self.channel.history(limit=None)]
        transcript = "\n".join([f"{m.author}: {m.content}" for m in reversed(messages)])

        log_channel = bot.get_channel(TICKET_LOG_CHANNEL_ID)
        embed = discord.Embed(
            title=f"📄 Ticket Closed - {self.channel.name}",
            description=f"Transcript:\n```{transcript[:4000]}```",
            color=discord.Color.green()
        )
        embed.set_footer(text=f"Closed by {interaction.user}", icon_url=interaction.user.display_avatar.url)
        await log_channel.send(embed=embed)
        await self.channel.delete()

# ---------------------------
# Verification Buttons
# ---------------------------
class VerificationView(discord.ui.View):
    def __init__(self, user, app):
        super().__init__(timeout=None)
        self.user = user
        self.app = app

    @discord.ui.button(label="✅ Verify", style=discord.ButtonStyle.green, emoji="✅")
    async def verify(self, interaction: discord.Interaction, button: discord.ui.Button):
        embed = discord.Embed(
            title=f"🎉 {self.app['name']} Verified!",
            description=f"Here is your app link: [Click Here]({self.app['link']})",
            color=discord.Color.green()
        )
        await self.user.send(embed=embed)
        await interaction.response.send_message("User verified successfully!", ephemeral=True)

    @discord.ui.button(label="❌ Decline", style=discord.ButtonStyle.red, emoji="❌")
    async def decline(self, interaction: discord.Interaction, button: discord.ui.Button):
        embed = discord.Embed(
            title="⚠️ Verification Declined",
            description="The subscription screenshot is invalid. Please try again.",
            color=discord.Color.red()
        )
        await self.user.send(embed=embed)
        await interaction.response.send_message("User declined.", ephemeral=True)

# ---------------------------
# Commands
# ---------------------------
@bot.tree.command(name="ticket", description="Open a support ticket 🎫")
async def ticket(interaction: discord.Interaction):
    view = TicketView(interaction.user)
    embed = discord.Embed(
        title="🎫 Support Ticket Booth",
        description="Click the button below to create a ticket and get assistance from our Staff team!",
        color=discord.Color.blurple()
    )
    embed.set_footer(text="Rash Tech Support", icon_url=interaction.guild.icon.url if interaction.guild.icon else None)
    embed.set_thumbnail(url="https://i.imgur.com/7ZQv1Qz.png")
    await interaction.response.send_message(embed=embed, view=view)

@bot.tree.command(name="remove_cooldown", description="Remove ticket cooldown for a user (Admin only)")
@app_commands.describe(user="User to remove cooldown")
async def remove_cooldown(interaction: discord.Interaction, user: discord.Member):
    if not interaction.user.guild_permissions.administrator:
        await interaction.response.send_message("❌ You don't have permission.", ephemeral=True)
        return
    user_cooldowns.pop(user.id, None)
    await interaction.response.send_message(f"✅ Cooldown removed for {user.mention}.")

# ---------------------------
# Ready Event & Ticket Booth
# ---------------------------
@bot.event
async def on_ready():
    print(f"Logged in as {bot.user}")
    channel = discord.utils.get(bot.get_guild(GUILD_ID).channels, name="tickets")
    if channel:
        view = TicketView(user=None)
        embed = discord.Embed(
            title="🎫 Create Your Ticket",
            description="Click the button below to open a support ticket with our Staff team!",
            color=discord.Color.blurple()
        )
        embed.set_thumbnail(url="https://i.imgur.com/7ZQv1Qz.png")
        await channel.send(embed=embed, view=view)

# ---------------------------
# Ticket Message Listener for App Requests
# ---------------------------
@bot.event
async def on_message(message):
    if message.author.bot or not message.channel.name.startswith("ticket-"):
        return

    for app in apps:
        if app['name'].lower() in message.content.lower():
            embed = discord.Embed(
                title=f"📦 {app['name']} Verification Required",
                description="Please upload a screenshot of your subscription. Staff will verify it shortly.",
                color=discord.Color.gold()
            )
            embed.set_footer(text="Rash Tech Premium Apps")
            await message.channel.send(embed=embed)

            verification_channel = discord.utils.get(message.guild.text_channels, name="verification")
            if verification_channel:
                await verification_channel.send(
                    content=f"Verification request from {message.author.mention} for {app['name']}",
                    view=VerificationView(message.author, app)
                )
            break

    await bot.process_commands(message)

# ---------------------------
# Run Bot
# ---------------------------
bot.run(TOKEN)
