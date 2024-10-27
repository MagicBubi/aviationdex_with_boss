import discord
import time
import random
import string
import logging
import re

from discord import app_commands
from discord.ext import commands
from typing import TYPE_CHECKING, Optional, cast
from discord.ui import Button, View

from ballsdex.settings import settings
from ballsdex.core.utils.transformers import BallInstanceTransform
from ballsdex.core.utils.transformers import BallEnabledTransform
from ballsdex.core.utils.transformers import SpecialTransform, BallTransform
from ballsdex.core.utils.paginator import FieldPageSource, Pages
from ballsdex.core.utils.logging import log_action
from ballsdex.settings import settings

if TYPE_CHECKING:
    from ballsdex.core.bot import BallsDexBot

log = logging.getLogger("ballsdex.packages.boss.cog")
FILENAME_RE = re.compile(r"^(.+)(\.\S+)$")

from ballsdex.core.models import (
    Ball,
    BallInstance,
    BlacklistedGuild,
    BlacklistedID,
    GuildConfig,
    Player,
    Trade,
    TradeObject,
    balls,
    specials,
)

# IMPORTANT NOTES, READ BEFORE USING
# 1. YOU MUST HAVE A SPECIAL CALLED "Boss" IN YOUR DEX, THIS IS FOR REWARDING THE WINNER.
#    MAKE IT SO THE SPECIAL'S END DATE IS BEFORE TODAY'S DATE
# 2. ONLY USE A COUNTRYBALL AS A BOSS in /boss start IF IT HAS BOTH THE COLLECTIBLE AND WILD CARDS STORED,
#    OTHERWISE THIS WILL RESULT TO AN ERROR.
#    Sometimes, you might create a non-spawnable ball using /admin balls create command, if that's the case
#    there's a chance you may have not selected a wild card as it isn't required.
#    Cards without wild cards do not work as a boss, as again, this will result in an error.
#    If you are using a ball made from the admin panel for the boss, then it's fine, since admin panel requires wild card.
# 3. You may change the shiny buffs below to suit your dex better (Line 264-266), it's defaulted at 1000 HP & ATK Bonus
# 4. Please report all bugs to user @moofficial on discord
# 5. Make sure to add "boss" to PACKAGES at ballsdex/core/bot.py (Usually around line 48)
# 6. Finally, add the boss folder to ballsdex/packages folder

# HOW TO PLAY
# Some commands can only be used by admins, these control the boss actions.
# 1. Start the boss using /boss start command. (ADMINS ONLY)
#    Choose a countryball to be the boss (required). Choose HP (Optional, Defaulted at 40000)
# 2. Players can join using /boss join command.
# 3. Start a round using /boss defend or /boss attack.(ADMINS ONLY)
#    With /boss attack you can choose how much attack the boss deals (Optional, Defaulted to RNG from 0 to 2000)
# 4. Players now choose an item to use against the boss using /boss select
# 5. /boss end_round ends the current round and displays user permformance about the round (ADMIN ONLY)
# 6. Step 3-5 is repeated until the boss' HP runs out, but you can end early with Step 7.
# 7. /boss_conclude ends the boss battle and rewards the winner, but you can choose to *not* reward the winner (ADMIN ONLY)


@app_commands.guilds(*settings.admin_guild_ids)
class Boss(commands.GroupCog):
    """
    Boss commands.
    """

    def __init__(self, bot: "BallsDexBot"):
        self.bot = bot
        self.boss_enabled = False
        self.balls = []
        self.users = []
        self.usersdamage = []
        self.usersinround = []
        self.currentvalue = ("")
        self.bossHP = 40000
        self.picking = False
        self.round = 0
        self.attack = False
        self.bossattack = 0
        self.bossball = None
        self.bosswild = None

    @app_commands.command()
    @app_commands.checks.has_any_role(*settings.root_role_ids, *settings.admin_role_ids)
    async def start(self, interaction: discord.Interaction, ball: BallTransform, hp_amount: int | None = None,):
        """
        Start the boss
        """
        if self.boss_enabled == True:
            return await interaction.response.send_message(f"There is already an ongoing boss battle", ephemeral=True)
        self.bossHP = (hp_amount if hp_amount is not None else 40000)
        def generate_random_name():
            source = string.ascii_uppercase + string.ascii_lowercase + string.ascii_letters
            return "".join(random.choices(source, k=15))
        extension = ball.collection_card.split(".")[-1]
        file_location = "." + ball.collection_card
        file_name = f"nt_{generate_random_name()}.{extension}"
        await interaction.response.send_message((f"# The boss battle has begun!\n-# HP: {self.bossHP}"),file=discord.File(file_location, filename=file_name),)
        await interaction.followup.send("Use `/boss join` to join the battle!")
        if ball != None:
            self.boss_enabled = True
            self.bossball = ball

            extension = ball.wild_card.split(".")[-1]
            file_location = "." + ball.wild_card
            file_name = f"nt_{generate_random_name()}.{extension}"
            self.bosswild = file=discord.File(file_location, filename=file_name)

    @app_commands.command()
    @app_commands.checks.has_any_role(*settings.root_role_ids, *settings.admin_role_ids)
    async def attack(self, interaction: discord.Interaction, attack_amount: int | None = None):
        """
        Start a round where the Boss Attacks
        """
        if not self.boss_enabled:
            return await interaction.response.send_message("Boss is disabled", ephemeral=True)
        if self.picking:
            return await interaction.response.send_message("There is already an ongoing round", ephemeral=True)
        if len(self.users) == 0:
            return await interaction.response.send_message("There are not enough users to start the round", ephemeral=True)
        if self.bossHP <= 0:
            return await interaction.response.send_message("The Boss is dead", ephemeral=True)
        self.round += 1

        def generate_random_name():
            source = string.ascii_uppercase + string.ascii_lowercase + string.ascii_letters
            return "".join(random.choices(source, k=15))
        extension = self.bossball.wild_card.split(".")[-1]
        file_location = "." + self.bossball.wild_card
        file_name = f"nt_{generate_random_name()}.{extension}"
        await interaction.response.send_message(
            (f"Round {self.round}\n# {self.bossball.country} is preparing to attack!"),file=discord.File(file_location, filename=file_name)
        )
        await interaction.followup.send(f"Use `/boss select` to select your defending {settings.collectible_name}.\nYour selected {settings.collectible_name}'s HP will be used to defend.")
        self.picking = True
        self.attack = True
        self.bossattack = (attack_amount if attack_amount is not None else random.randrange(0, 2000, 100))

    @app_commands.command()
    @app_commands.checks.has_any_role(*settings.root_role_ids, *settings.admin_role_ids)
    async def defend(self, interaction: discord.Interaction):
        """
        Start a round where the Boss Defends
        """
        if not self.boss_enabled:
            return await interaction.response.send_message("Boss is disabled", ephemeral=True)
        if self.picking:
            return await interaction.response.send_message("There is already an ongoing round", ephemeral=True)
        if len(self.users) == 0:
            return await interaction.response.send_message("There are not enough users to start the round", ephemeral=True)
        if self.bossHP <= 0:
            return await interaction.response.send_message("The Boss is dead", ephemeral=True)
        self.round += 1

        def generate_random_name():
            source = string.ascii_uppercase + string.ascii_lowercase + string.ascii_letters
            return "".join(random.choices(source, k=15))
        extension = self.bossball.wild_card.split(".")[-1]
        file_location = "." + self.bossball.wild_card
        file_name = f"nt_{generate_random_name()}.{extension}"
        await interaction.response.send_message(
            (f"Round {self.round}\n# {self.bossball.country} is preparing to defend!"),file=discord.File(file_location, filename=file_name)
        )
        await interaction.followup.send(f"Use `/boss select` to select your attacking {settings.collectible_name}.\nYour selected {settings.collectible_name}'s ATK will be used to attack.")
        self.picking = True
        self.attack = False


    @app_commands.command()
    @app_commands.checks.has_any_role(*settings.root_role_ids, *settings.admin_role_ids)
    async def end_round(self, interaction: discord.Interaction):
        """
        End the current round
        """
        if not self.boss_enabled:
            return await interaction.response.send_message("Boss is disabled", ephemeral=True)
        if not self.picking:
            return await interaction.response.send_message(
                f"There are no ongoing rounds, use `/boss attack` or `/boss defend` to start one", ephemeral=True
            )
        self.picking = False
        if not self.attack:
            if int(self.bossHP) <= 0:
                await interaction.response.send_message(
                    f"{self.currentvalue}There is 0 HP remaining on the boss, the boss has been defeated!",
                )
            else:
                await interaction.response.send_message(
                    f"{self.currentvalue}There is {self.bossHP} HP remaining on the boss",
                )
        else:
            snapshotusers = self.users.copy()
            for user in snapshotusers:
                if str(user) not in self.currentvalue:
                    self.currentvalue += ("<@"+str(user)+"> has not picked on time and ***died!***\n")
                    self.users.remove(user)
            if len(self.users) == 0:
                await interaction.response.send_message(
                    f"The boss has dealt {self.bossattack} damage!\n{self.currentvalue}The boss has won!",
                )
            else:
                await interaction.response.send_message(
                    f"The boss has dealt {self.bossattack} damage!\n{self.currentvalue}",
                )
        self.currentvalue = ("")

    @ app_commands.command()
    @ app_commands.checks.has_any_role(*settings.root_role_ids, *settings.admin_role_ids)
    async def peek(self, interaction: discord.Interaction):
        """
        See current stats of the boss
        """
        return await interaction.response.send_message(
            f"CurrentValue:{self.currentvalue}\nUsers:{self.users}\n\nUsersDamage:{self.usersdamage}\n\nBalls:{self.balls}\n\nUsersInRound:{self.usersinround}", ephemeral=True
        )




    @app_commands.command()
    async def select(self, interaction: discord.Interaction, ball: BallInstanceTransform):
        """
        Select an countryball to use against the boss.
        """
        if [int(interaction.user.id),self.round] in self.usersinround:
            return await interaction.response.send_message(
                f"You have already selected an {settings.collectible_name}", ephemeral=True
            )
        if not self.boss_enabled:
            return await interaction.response.send_message("Boss is disabled", ephemeral=True)
        if not self.picking:
            return await interaction.response.send_message(f"It is not yet time to select an {settings.collectible_name}", ephemeral=True)
        if interaction.user.id not in self.users:
            return await interaction.response.send_message(
                "You have not Joined the Boss Battle, or you have died!", ephemeral=True
            )
        if ball in self.balls:
            return await interaction.response.send_message(
                f"You cannot select the same {settings.collectible_name} twice", ephemeral=True
            )
        if ball == None:
            return
        self.balls.append(ball)
        self.usersinround.append([int(interaction.user.id),self.round])
        if ball.attack > 1000000: #maximum and minimum atk and hp stats 
            ballattack = 1000000
        elif ball.attack < 0:
            ballattack = 0
        else:
            ballattack = ball.attack
        if ball.health > 1000000:
            ballhealth = 1000000
        elif ball.health < 0:
            ballhealth = 0
        else:
            ballhealth = ball.health
        messageforuser = f"{ball.description(short=True, include_emoji=True, bot=self.bot)}has been selected for this round, with {ballattack} ATK and {ballhealth} HP"
        if "✨" in messageforuser:
            messageforuser = f"{ball.description(short=True, include_emoji=True, bot=self.bot)}has been selected for this round, with {ballattack}+1000 ATK and {ballhealth}+1000 HP"
            ballhealth += 1000
            ballattack += 1000
        else:
            pass

        if not self.attack:
            self.bossHP -= ballattack
            self.usersdamage.append([int(interaction.user.id),ballattack])
            self.currentvalue += ("<@"+str(interaction.user.id)+">'s "+str(ball.description(short=True, include_emoji=True, bot=self.bot))+" has dealt "+(str(ballattack))+" damage!\n")
        else:
            if self.bossattack >= ballhealth:
                self.users.remove(interaction.user.id)
                self.currentvalue += ("<@"+str(interaction.user.id)+">'s "+str(ball.description(short=True, include_emoji=True, bot=self.bot))+" had "+(str(ballhealth))+"HP and ***died!***\n")
            else:
                self.currentvalue += ("<@" + str(interaction.user.id) + ">'s " + str(ball.description(short=True, include_emoji=True, bot=self.bot)) + " had " + (str(ballhealth)) + "HP and ***survived!***\n")

        await interaction.response.send_message(
            messageforuser, ephemeral=True
        )

    @app_commands.command()
    @app_commands.checks.has_any_role(*settings.root_role_ids, *settings.admin_role_ids)
    async def conclude(self, interaction: discord.Interaction, do_not_reward: bool | None = False,):
        """
        Finish the boss, conclude the Winner
        """
        self.picking = False
        self.boss_enabled = False
        test = self.usersdamage
        test2 = []
        total = ("")
        totalnum = []
        for i in range(len(test)):
            if test[i][0] not in test2 and test[i][0] in self.users:
                temp = 0
                tempvalue = test[i][0]
                test2.append(tempvalue)
                for j in range(len(test)):
                    if test[j][0] == tempvalue:
                        temp += test[j][1]
                total += ("<@" + str(tempvalue) + "> has dealt a total of " + str(temp) + " damage!\n")
                totalnum.append([tempvalue, temp])
        bosswinner = 0
        highest = 0
        for k in range(len(totalnum)):
            if totalnum[k][1] > highest:
                highest = totalnum[k][1]
                bosswinner = totalnum[k][0]
        if bosswinner == 0:
            self.round = 0
            self.balls = []
            self.users = []
            self.currentvalue = ("")
            self.usersdamage = []
            self.usersinround = []
            self.bossHP = 40000
            self.round = 0
            self.attack = False
            self.bossattack = 0
            self.bossball = None
            self.bosswild = None
            return await interaction.response.send_message(f"BOSS HAS CONCLUDED\nThe boss has won the Boss Battle!")
        if do_not_reward == False:
            await interaction.response.defer(thinking=True)
            player, created = await Player.get_or_create(discord_id=bosswinner)
            special = special = [x for x in specials.values() if x.name == "Boss"][0]
            instance = await BallInstance.create(
                ball=self.bossball,
                player=player,
                shiny=False,
                special=special,
                attack_bonus=0,
                health_bonus=0,
            )
            await interaction.followup.send(
                f"BOSS HAS CONCLUDED.\n{total}\n<@{bosswinner}> has won the Boss Battle!\n\n"
                f"`{self.bossball.country}` {settings.collectible_name} was successfully given to *<@{bosswinner}>*.\n"
                f"ATK:`0` • Special: `Boss`\n"
                f"HP:`0` • Shiny: `None`"
            )
            await log_action(
                f"`BOSS REWARDS` gave {settings.collectible_name} {self.bossball.country} to *<@{bosswinner}>*"
                f"Special=Boss ATK=0 "
                f"HP=0 shiny=None",
                self.bot,
            )
        else:
            await interaction.response.send_message(f"BOSS HAS CONCLUDED.\n{total}\n<@{bosswinner}> has won the Boss Battle!\n\n")
        self.round = 0
        self.balls = []
        self.users = []
        self.currentvalue = ("")
        self.usersdamage = []
        self.usersinround = []
        self.bossHP = 40000
        self.round = 0
        self.attack = False
        self.bossattack = 0
        self.bossball = None
        self.bosswild = None

    @app_commands.command()
    async def join(self, interaction: discord.Interaction):
        """
        Join the boss battle!.
        """
        if not self.boss_enabled:
            return await interaction.response.send_message("Boss is disabled", ephemeral=True)
        if [int(interaction.user.id),self.round] in self.usersinround:
            return await interaction.response.send_message("You have already joined the boss", ephemeral=True)
        if self.round != 0 and interaction.user.id not in self.users:
            return await interaction.response.send_message(
                "It is too late to join the boss, or you have died", ephemeral=True
            )
        if interaction.user.id in self.users:
            return await interaction.response.send_message(
                "You have already joined the boss", ephemeral=True
            )
        self.users.append(interaction.user.id)
        await interaction.response.send_message(
            "You have joined the Boss Battle!", ephemeral=True
        )

    def test(self, interaction: discord.Interaction):
        if [int(interaction.user.id),self.round] in self.usersinround:
            return ("You have already joined the boss")
        if self.round != 0 and interaction.user.id not in self.users:
            return ("It is too late to join the boss, or you have died")
        if interaction.user.id in self.users:
            return ("You have already joined the boss")
        self.users.append(interaction.user.id)
        return ("You have joined the Boss Battle!")


