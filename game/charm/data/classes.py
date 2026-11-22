"""Classes, titles (title_table[class][level][male, female]) and poses (pose_table[pose][0][message]).

Generated from the C by charm_tools port data until cut-over (the c-final tag); edited by hand since
(#112, decision 4).

Tables: class_table (const.c). A C table that ends with a NULL sentinel row is scanned up to it; that row isn't
here.

Part of Charm, derived from DikuMUD (c) 1990-91 Sebastian Hammer, Michael Seifert, Hans Henrik Staerfeldt,
Tom Madsen and Katja Nyboe; Merc (c) 1992-93 Michael Chastain, Michael Quan and Mitchell Tse; and ROM 2.4
(c) 1993-98 Russ Taylor. Ported from src/act_comm.c, src/const.c. Licence terms: README.md#licence-terms and doc/.
"""

from charm.data.structs import ClassType

# class_table, const.c
CLASS_TABLE = (
    ClassType(
        name="mage",
        who_name="Mag",
        attr_prime=1,
        weapon=3701,
        guild=(3018, 9618),
        skill_adept=75,
        thac0_00=20,
        thac0_32=6,
        hp_min=6,
        hp_max=8,
        fMana=True,
        base_group="mage basics",
        default_group="mage default",
    ),
    ClassType(
        name="cleric",
        who_name="Cle",
        attr_prime=2,
        weapon=3700,
        guild=(3003, 9619),
        skill_adept=75,
        thac0_00=20,
        thac0_32=2,
        hp_min=7,
        hp_max=10,
        fMana=True,
        base_group="cleric basics",
        default_group="cleric default",
    ),
    ClassType(
        name="thief",
        who_name="Thi",
        attr_prime=3,
        weapon=3701,
        guild=(3028, 9639),
        skill_adept=75,
        thac0_00=20,
        thac0_32=-4,
        hp_min=8,
        hp_max=13,
        fMana=False,
        base_group="thief basics",
        default_group="thief default",
    ),
    ClassType(
        name="warrior",
        who_name="War",
        attr_prime=0,
        weapon=3702,
        guild=(3022, 9633),
        skill_adept=75,
        thac0_00=20,
        thac0_32=-10,
        hp_min=11,
        hp_max=15,
        fMana=False,
        base_group="warrior basics",
        default_group="warrior default",
    ),
)

# title_table, const.c
TITLE_TABLE = ((("Man", "Woman"), ("Apprentice of Magic", "Apprentice of Magic"), ("Spell Student", "Spell Student"), ("Scholar of Magic", "Scholar of Magic"), ("Delver in Spells", "Delveress in Spells"), ("Medium of Magic", "Medium of Magic"), ("Scribe of Magic", "Scribess of Magic"), ("Seer", "Seeress"), ("Sage", "Sage"), ("Illusionist", "Illusionist"), ("Abjurer", "Abjuress"), ("Invoker", "Invoker"), ("Enchanter", "Enchantress"), ("Conjurer", "Conjuress"), ("Magician", "Witch"), ("Creator", "Creator"), ("Savant", "Savant"), ("Magus", "Craftess"), ("Wizard", "Wizard"), ("Warlock", "War Witch"), ("Sorcerer", "Sorceress"), ("Elder Sorcerer", "Elder Sorceress"), ("Grand Sorcerer", "Grand Sorceress"), ("Great Sorcerer", "Great Sorceress"), ("Golem Maker", "Golem Maker"), ("Greater Golem Maker", "Greater Golem Maker"), ("Maker of Stones", "Maker of Stones"), ("Maker of Potions", "Maker of Potions"), ("Maker of Scrolls", "Maker of Scrolls"), ("Maker of Wands", "Maker of Wands"), ("Maker of Staves", "Maker of Staves"), ("Demon Summoner", "Demon Summoner"), ("Greater Demon Summoner", "Greater Demon Summoner"), ("Dragon Charmer", "Dragon Charmer"), ("Greater Dragon Charmer", "Greater Dragon Charmer"), ("Master of all Magic", "Master of all Magic"), ("Master Mage", "Master Mage"), ("Master Mage", "Master Mage"), ("Master Mage", "Master Mage"), ("Master Mage", "Master Mage"), ("Master Mage", "Master Mage"), ("Master Mage", "Master Mage"), ("Master Mage", "Master Mage"), ("Master Mage", "Master Mage"), ("Master Mage", "Master Mage"), ("Master Mage", "Master Mage"), ("Master Mage", "Master Mage"), ("Master Mage", "Master Mage"), ("Master Mage", "Master Mage"), ("Master Mage", "Master Mage"), ("Master Mage", "Master Mage"), ("Mage Hero", "Mage Heroine"), ("Avatar of Magic", "Avatar of Magic"), ("Angel of Magic", "Angel of Magic"), ("Demigod of Magic", "Demigoddess of Magic"), ("Immortal of Magic", "Immortal of Magic"), ("God of Magic", "Goddess of Magic"), ("Deity of Magic", "Deity of Magic"), ("Supremity of Magic", "Supremity of Magic"), ("Creator", "Creator"), ("Implementor", "Implementress")), (("Man", "Woman"), ("Believer", "Believer"), ("Attendant", "Attendant"), ("Acolyte", "Acolyte"), ("Novice", "Novice"), ("Missionary", "Missionary"), ("Adept", "Adept"), ("Deacon", "Deaconess"), ("Vicar", "Vicaress"), ("Priest", "Priestess"), ("Minister", "Lady Minister"), ("Canon", "Canon"), ("Levite", "Levitess"), ("Curate", "Curess"), ("Monk", "Nun"), ("Healer", "Healess"), ("Chaplain", "Chaplain"), ("Expositor", "Expositress"), ("Bishop", "Bishop"), ("Arch Bishop", "Arch Lady of the Church"), ("Patriarch", "Matriarch"), ("Elder Patriarch", "Elder Matriarch"), ("Grand Patriarch", "Grand Matriarch"), ("Great Patriarch", "Great Matriarch"), ("Demon Killer", "Demon Killer"), ("Greater Demon Killer", "Greater Demon Killer"), ("Cardinal of the Sea", "Cardinal of the Sea"), ("Cardinal of the Earth", "Cardinal of the Earth"), ("Cardinal of the Air", "Cardinal of the Air"), ("Cardinal of the Ether", "Cardinal of the Ether"), ("Cardinal of the Heavens", "Cardinal of the Heavens"), ("Avatar of an Immortal", "Avatar of an Immortal"), ("Avatar of a Deity", "Avatar of a Deity"), ("Avatar of a Supremity", "Avatar of a Supremity"), ("Avatar of an Implementor", "Avatar of an Implementor"), ("Master of all Divinity", "Mistress of all Divinity"), ("Master Cleric", "Master Cleric"), ("Master Cleric", "Master Cleric"), ("Master Cleric", "Master Cleric"), ("Master Cleric", "Master Cleric"), ("Master Cleric", "Master Cleric"), ("Master Cleric", "Master Cleric"), ("Master Cleric", "Master Cleric"), ("Master Cleric", "Master Cleric"), ("Master Cleric", "Master Cleric"), ("Master Cleric", "Master Cleric"), ("Master Cleric", "Master Cleric"), ("Master Cleric", "Master Cleric"), ("Master Cleric", "Master Cleric"), ("Master Cleric", "Master Cleric"), ("Master Cleric", "Master Cleric"), ("Holy Hero", "Holy Heroine"), ("Holy Avatar", "Holy Avatar"), ("Angel", "Angel"), ("Demigod", "Demigoddess"), ("Immortal", "Immortal"), ("God", "Goddess"), ("Deity", "Deity"), ("Supreme Master", "Supreme Mistress"), ("Creator", "Creator"), ("Implementor", "Implementress")), (("Man", "Woman"), ("Pilferer", "Pilferess"), ("Footpad", "Footpad"), ("Filcher", "Filcheress"), ("Pick-Pocket", "Pick-Pocket"), ("Sneak", "Sneak"), ("Pincher", "Pincheress"), ("Cut-Purse", "Cut-Purse"), ("Snatcher", "Snatcheress"), ("Sharper", "Sharpress"), ("Rogue", "Rogue"), ("Robber", "Robber"), ("Magsman", "Magswoman"), ("Highwayman", "Highwaywoman"), ("Burglar", "Burglaress"), ("Thief", "Thief"), ("Knifer", "Knifer"), ("Quick-Blade", "Quick-Blade"), ("Killer", "Murderess"), ("Brigand", "Brigand"), ("Cut-Throat", "Cut-Throat"), ("Spy", "Spy"), ("Grand Spy", "Grand Spy"), ("Master Spy", "Master Spy"), ("Assassin", "Assassin"), ("Greater Assassin", "Greater Assassin"), ("Master of Vision", "Mistress of Vision"), ("Master of Hearing", "Mistress of Hearing"), ("Master of Smell", "Mistress of Smell"), ("Master of Taste", "Mistress of Taste"), ("Master of Touch", "Mistress of Touch"), ("Crime Lord", "Crime Mistress"), ("Infamous Crime Lord", "Infamous Crime Mistress"), ("Greater Crime Lord", "Greater Crime Mistress"), ("Master Crime Lord", "Master Crime Mistress"), ("Godfather", "Godmother"), ("Master Thief", "Master Thief"), ("Master Thief", "Master Thief"), ("Master Thief", "Master Thief"), ("Master Thief", "Master Thief"), ("Master Thief", "Master Thief"), ("Master Thief", "Master Thief"), ("Master Thief", "Master Thief"), ("Master Thief", "Master Thief"), ("Master Thief", "Master Thief"), ("Master Thief", "Master Thief"), ("Master Thief", "Master Thief"), ("Master Thief", "Master Thief"), ("Master Thief", "Master Thief"), ("Master Thief", "Master Thief"), ("Master Thief", "Master Thief"), ("Assassin Hero", "Assassin Heroine"), ("Avatar of Death", "Avatar of Death"), ("Angel of Death", "Angel of Death"), ("Demigod of Assassins", "Demigoddess of Assassins"), ("Immortal Assasin", "Immortal Assassin"), ("God of Assassins", "God of Assassins"), ("Deity of Assassins", "Deity of Assassins"), ("Supreme Master", "Supreme Mistress"), ("Creator", "Creator"), ("Implementor", "Implementress")), (("Man", "Woman"), ("Swordpupil", "Swordpupil"), ("Recruit", "Recruit"), ("Sentry", "Sentress"), ("Fighter", "Fighter"), ("Soldier", "Soldier"), ("Warrior", "Warrior"), ("Veteran", "Veteran"), ("Swordsman", "Swordswoman"), ("Fencer", "Fenceress"), ("Combatant", "Combatess"), ("Hero", "Heroine"), ("Myrmidon", "Myrmidon"), ("Swashbuckler", "Swashbuckleress"), ("Mercenary", "Mercenaress"), ("Swordmaster", "Swordmistress"), ("Lieutenant", "Lieutenant"), ("Champion", "Lady Champion"), ("Dragoon", "Lady Dragoon"), ("Cavalier", "Lady Cavalier"), ("Knight", "Lady Knight"), ("Grand Knight", "Grand Knight"), ("Master Knight", "Master Knight"), ("Paladin", "Paladin"), ("Grand Paladin", "Grand Paladin"), ("Demon Slayer", "Demon Slayer"), ("Greater Demon Slayer", "Greater Demon Slayer"), ("Dragon Slayer", "Dragon Slayer"), ("Greater Dragon Slayer", "Greater Dragon Slayer"), ("Underlord", "Underlord"), ("Overlord", "Overlord"), ("Baron of Thunder", "Baroness of Thunder"), ("Baron of Storms", "Baroness of Storms"), ("Baron of Tornadoes", "Baroness of Tornadoes"), ("Baron of Hurricanes", "Baroness of Hurricanes"), ("Baron of Meteors", "Baroness of Meteors"), ("Master Warrior", "Master Warrior"), ("Master Warrior", "Master Warrior"), ("Master Warrior", "Master Warrior"), ("Master Warrior", "Master Warrior"), ("Master Warrior", "Master Warrior"), ("Master Warrior", "Master Warrior"), ("Master Warrior", "Master Warrior"), ("Master Warrior", "Master Warrior"), ("Master Warrior", "Master Warrior"), ("Master Warrior", "Master Warrior"), ("Master Warrior", "Master Warrior"), ("Master Warrior", "Master Warrior"), ("Master Warrior", "Master Warrior"), ("Master Warrior", "Master Warrior"), ("Master Warrior", "Master Warrior"), ("Knight Hero", "Knight Heroine"), ("Avatar of War", "Avatar of War"), ("Angel of War", "Angel of War"), ("Demigod of War", "Demigoddess of War"), ("Immortal Warlord", "Immortal Warlord"), ("God of War", "God of War"), ("Deity of War", "Deity of War"), ("Supreme Master of War", "Supreme Mistress of War"), ("Creator", "Creator"), ("Implementor", "Implementress")))

# pose_table, act_comm.c
POSE_TABLE = ((("You sizzle with energy.", "$n sizzles with energy.", "You feel very holy.", "$n looks very holy.", "You perform a small card trick.", "$n performs a small card trick.", "You show your bulging muscles.", "$n shows $s bulging muscles."),), (("You turn into a butterfly, then return to your normal shape.", "$n turns into a butterfly, then returns to $s normal shape.", "You nonchalantly turn wine into water.", "$n nonchalantly turns wine into water.", "You wiggle your ears alternately.", "$n wiggles $s ears alternately.", "You crack nuts between your fingers.", "$n cracks nuts between $s fingers."),), (("Blue sparks fly from your fingers.", "Blue sparks fly from $n's fingers.", "A halo appears over your head.", "A halo appears over $n's head.", "You nimbly tie yourself into a knot.", "$n nimbly ties $mself into a knot.", "You grizzle your teeth and look mean.", "$n grizzles $s teeth and looks mean."),), (("Little red lights dance in your eyes.", "Little red lights dance in $n's eyes.", "You recite words of wisdom.", "$n recites words of wisdom.", "You juggle with daggers, apples, and eyeballs.", "$n juggles with daggers, apples, and eyeballs.", "You hit your head, and your eyes roll.", "$n hits $s head, and $s eyes roll."),), (("A slimy green monster appears before you and bows.", "A slimy green monster appears before $n and bows.", "Deep in prayer, you levitate.", "Deep in prayer, $n levitates.", "You steal the underwear off every person in the room.", "Your underwear is gone!  $n stole it!", "Crunch, crunch -- you munch a bottle.", "Crunch, crunch -- $n munches a bottle."),), (("You turn everybody into a little pink elephant.", "You are turned into a little pink elephant by $n.", "An angel consults you.", "An angel consults $n.", "The dice roll ... and you win again.", "The dice roll ... and $n wins again.", "... 98, 99, 100 ... you do pushups.", "... 98, 99, 100 ... $n does pushups."),), (("A small ball of light dances on your fingertips.", "A small ball of light dances on $n's fingertips.", "Your body glows with an unearthly light.", "$n's body glows with an unearthly light.", "You count the money in everyone's pockets.", "Check your money, $n is counting it.", "Arnold Schwarzenegger admires your physique.", "Arnold Schwarzenegger admires $n's physique."),), (("Smoke and fumes leak from your nostrils.", "Smoke and fumes leak from $n's nostrils.", "A spot light hits you.", "A spot light hits $n.", "You balance a pocket knife on your tongue.", "$n balances a pocket knife on your tongue.", "Watch your feet, you are juggling granite boulders.", "Watch your feet, $n is juggling granite boulders."),), (("The light flickers as you rap in magical languages.", "The light flickers as $n raps in magical languages.", "Everyone levitates as you pray.", "You levitate as $n prays.", "You produce a coin from everyone's ear.", "$n produces a coin from your ear.", "Oomph!  You squeeze water out of a granite boulder.", "Oomph!  $n squeezes water out of a granite boulder."),), (("Your head disappears.", "$n's head disappears.", "A cool breeze refreshes you.", "A cool breeze refreshes $n.", "You step behind your shadow.", "$n steps behind $s shadow.", "You pick your teeth with a spear.", "$n picks $s teeth with a spear."),), (("A fire elemental singes your hair.", "A fire elemental singes $n's hair.", "The sun pierces through the clouds to illuminate you.", "The sun pierces through the clouds to illuminate $n.", "Your eyes dance with greed.", "$n's eyes dance with greed.", "Everyone is swept off their foot by your hug.", "You are swept off your feet by $n's hug."),), (("The sky changes color to match your eyes.", "The sky changes color to match $n's eyes.", "The ocean parts before you.", "The ocean parts before $n.", "You deftly steal everyone's weapon.", "$n deftly steals your weapon.", "Your karate chop splits a tree.", "$n's karate chop splits a tree."),), (("The stones dance to your command.", "The stones dance to $n's command.", "A thunder cloud kneels to you.", "A thunder cloud kneels to $n.", "The Grey Mouser buys you a beer.", "The Grey Mouser buys $n a beer.", "A strap of your armor breaks over your mighty thews.", "A strap of $n's armor breaks over $s mighty thews."),), (("The heavens and grass change colour as you smile.", "The heavens and grass change colour as $n smiles.", "The Burning Man speaks to you.", "The Burning Man speaks to $n.", "Everyone's pocket explodes with your fireworks.", "Your pocket explodes with $n's fireworks.", "A boulder cracks at your frown.", "A boulder cracks at $n's frown."),), (("Everyone's clothes are transparent, and you are laughing.", "Your clothes are transparent, and $n is laughing.", "An eye in a pyramid winks at you.", "An eye in a pyramid winks at $n.", "Everyone discovers your dagger a centimeter from their eye.", "You discover $n's dagger a centimeter from your eye.", "Mercenaries arrive to do your bidding.", "Mercenaries arrive to do $n's bidding."),), (("A black hole swallows you.", "A black hole swallows $n.", "Valentine Michael Smith offers you a glass of water.", "Valentine Michael Smith offers $n a glass of water.", "Where did you go?", "Where did $n go?", "Four matched Percherons bring in your chariot.", "Four matched Percherons bring in $n's chariot."),), (("The world shimmers in time with your whistling.", "The world shimmers in time with $n's whistling.", "The great god Mota gives you a staff.", "The great god Mota gives $n a staff.", "Click.", "Click.", "Atlas asks you to relieve him.", "Atlas asks $n to relieve him."),))
