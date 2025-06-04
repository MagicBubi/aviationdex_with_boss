from ballsdex.core.utils.transformers import BallTransform
import discord
import random
from discord import app_commands
from discord.ext import commands
from datetime import datetime

from ballsdex.core.models import BallInstance, Player, balls, specials
from ballsdex.settings import settings
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ballsdex.core.bot import BallsDexBot

# Define rarity range-based goals
RARITY_COLLECTION_GOALS = [
    ((0.0009, 0.0022), 3),          # Secret
    ((0.0022, 0.05), 8),            # TX
    ((0.05, 0.06), 15),             # T1
    ((0.06, 0.065), 20),            # T2
    ((0.065, 0.07), 25),            # T3
    ((0.07, 0.11), 30),             # T4
    ((0.11, 0.17), 35),             # T5
    ((0.17, 0.2), 40),              # T6
    ((0.2, 0.25), 50),              # T7
    ((0.25, 0.3), 60),              # T8
    ((0.3, 0.4), 70),               # T9
    ((0.4, 0.5), 80),               # T10
    ((0.5, 0.65), 90),              # T11
    ((0.65, 0.7), 105),             # T12
    ((0.7, 0.75), 120),             # T13
    ((0.75, 0.8), 135)              # T14
]

# Helper to get collection goal from rarity
def get_collection_goal_by_rarity(rarity: float) -> int:
    for (low, high), goal in RARITY_COLLECTION_GOALS:
        if low <= rarity < high:
            return goal
    return 25  # Fallback if not matched

class Collector(commands.GroupCog, group_name="collector"):
    """
    Collector Code command
    """
    def __init__(self, bot: "BallsDexBot"):
        self.bot = bot

    @app_commands.command()
    async def progress(self, interaction: discord.Interaction, plane: BallTransform):
        """
        Check the player's progress towards collecting enough collectibles to get the Collector card.

        Parameters:
        plane: BallTransform
            The plane you want to see progress for.
        """
        await interaction.response.defer(ephemeral=True, thinking=True)

        player = await Player.get_or_none(discord_id=interaction.user.id)
        if not player:
            await interaction.followup.send("You don't have any planes yet!", ephemeral=True)
            return

        # Fetch user's collectibles (balls)
        user_balls = await BallInstance.filter(player=player).select_related("ball")

        if not user_balls:
            await interaction.followup.send("You have no collectibles yet!", ephemeral=True)
            return

        # Filter balls to check for the specific flock (target collectible)
        target_ball_instances = [ball for ball in user_balls if ball.ball == plane]

        # Count the total number of specific flock balls the player has
        total_target_balls = len(target_ball_instances)

        # Get collection goal based on rarity range
        rarity = plane.rarity
        COLLECTION_GOAL = get_collection_goal_by_rarity(rarity)

        # Calculate remaining
        remaining = max(0, COLLECTION_GOAL - total_target_balls)

        # Send progress information
        embed = discord.Embed(title="Collection Progress", color=discord.Colour.from_rgb(168, 199, 247))
        embed.add_field(name="Total Collectibles", value=f"**{total_target_balls}** {plane.country}", inline=False)
        embed.add_field(name="Collectible Goal", value=f"**{COLLECTION_GOAL}**", inline=False)
        embed.add_field(name="Remaining to Unlock", value=f"**{remaining}**", inline=False)

        await interaction.followup.send(embed=embed, ephemeral=True)
    @app_commands.command()
    async def claim(self, interaction: discord.Interaction, plane: BallTransform):
        """
        Reward the user with the Collector card if they have collected enough items.

        Parameters:
        plane: BallTransform
            The flock you want to claim.
        """
        await interaction.response.defer(ephemeral=True, thinking=True)

        player = await Player.get_or_none(discord_id=interaction.user.id)
        if not player:
            await interaction.followup.send("You don't have any planes yet!", ephemeral=True)
            return

        user_balls = await BallInstance.filter(player=player).select_related("ball")

        if not user_balls:
            await interaction.followup.send("You have no collectibles yet!", ephemeral=True)
            return

        target_ball_instances = [ball for ball in user_balls if ball.ball_id == plane.pk]
        total_target_balls = len(target_ball_instances)

        rarity = plane.rarity
        COLLECTION_GOAL = get_collection_goal_by_rarity(rarity)

        special = next((x for x in specials.values() if x.name == "Collector"), None)
        if not special:
            await interaction.followup.send("Collector card not found! Please contact support.", ephemeral=True)
            return

        has_special_card = any(
            ball.special_id == special.pk and ball.ball.country == plane.country
            for ball in user_balls
        )

        if has_special_card:
            reward_text = "You already have the Collector card for this plane!"
        else:
            if total_target_balls >= COLLECTION_GOAL:
                special_ball = next(
                    (ball for ball in balls.values() if ball.country == plane.country),
                    None
                )
                if not special_ball:
                    await interaction.followup.send("Special ball not found! Please contact support.", ephemeral=True)
                    return

                await BallInstance.create(
                    ball=special_ball,
                    player=player,
                    server_id=interaction.guild_id,
                    attack_bonus=random.randint(-20, 20),
                    health_bonus=random.randint(-20, 20),
                    special=special
                )
                reward_text = "The Collector card has been added to your collection!"
            else:
                reward_text = f"You have **{total_target_balls}/{COLLECTION_GOAL}** {plane.country}'s. Keep grinding to unlock the Collector card!"

        embed = discord.Embed(title="Collector Card Reward", color=discord.Colour.from_rgb(168, 199, 247))
        embed.add_field(name="Total Collectibles", value=f"**{total_target_balls}** {plane.country}", inline=False)
        embed.add_field(name="Special Reward", value=reward_text, inline=False)
