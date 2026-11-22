"""Flag names (tables.c's flag_type tables), for flag_lookup, bit.c's flag_value and flag_string, and OLC.

Generated from the C by quickmud_tools port data until cut-over (the c-final tag); edited by hand since
(#112, decision 4).

Tables: act_flags (tables.c), affect_flags (tables.c), off_flags (tables.c), imm_flags (tables.c), plr_flags
(tables.c), form_flags (tables.c), part_flags (tables.c), comm_flags (tables.c), area_flags (tables.c), sex_flags
(tables.c), exit_flags (tables.c), door_resets (tables.c), room_flags (tables.c), sector_flags (tables.c),
type_flags (tables.c), extra_flags (tables.c), wear_flags (tables.c), apply_flags (tables.c), wear_loc_strings
(tables.c), wear_loc_flags (tables.c), container_flags (tables.c), ac_type (tables.c), size_flags (tables.c),
weapon_class (tables.c), weapon_type2 (tables.c), res_flags (tables.c), vuln_flags (tables.c), position_flags
(tables.c), portal_flags (tables.c), furniture_flags (tables.c), apply_types (tables.c). A C table that ends with a
NULL sentinel row is scanned up to it; that row isn't here.

Part of QuickMUD-Python, derived from DikuMUD (c) 1990-91 Sebastian Hammer, Michael Seifert, Hans Henrik Staerfeldt,
Tom Madsen and Katja Nyboe; Merc (c) 1992-93 Michael Chastain, Michael Quan and Mitchell Tse; and ROM 2.4
(c) 1993-98 Russ Taylor. Ported from src/tables.c. Licence terms: README.md#licence-terms and doc/.
"""

from quickmud.data.structs import FlagType

# act_flags, tables.c
ACT_FLAGS = (
    FlagType(name="npc", bit=1, settable=False),
    FlagType(name="sentinel", bit=2, settable=True),
    FlagType(name="scavenger", bit=4, settable=True),
    FlagType(name="aggressive", bit=32, settable=True),
    FlagType(name="stay_area", bit=64, settable=True),
    FlagType(name="wimpy", bit=128, settable=True),
    FlagType(name="pet", bit=256, settable=True),
    FlagType(name="train", bit=512, settable=True),
    FlagType(name="practice", bit=1024, settable=True),
    FlagType(name="undead", bit=16384, settable=True),
    FlagType(name="cleric", bit=65536, settable=True),
    FlagType(name="mage", bit=131072, settable=True),
    FlagType(name="thief", bit=262144, settable=True),
    FlagType(name="warrior", bit=524288, settable=True),
    FlagType(name="noalign", bit=1048576, settable=True),
    FlagType(name="nopurge", bit=2097152, settable=True),
    FlagType(name="outdoors", bit=4194304, settable=True),
    FlagType(name="indoors", bit=16777216, settable=True),
    FlagType(name="healer", bit=67108864, settable=True),
    FlagType(name="gain", bit=134217728, settable=True),
    FlagType(name="update_always", bit=268435456, settable=True),
    FlagType(name="changer", bit=536870912, settable=True),
)

# affect_flags, tables.c
AFFECT_FLAGS = (
    FlagType(name="blind", bit=1, settable=True),
    FlagType(name="invisible", bit=2, settable=True),
    FlagType(name="detect_evil", bit=4, settable=True),
    FlagType(name="detect_invis", bit=8, settable=True),
    FlagType(name="detect_magic", bit=16, settable=True),
    FlagType(name="detect_hidden", bit=32, settable=True),
    FlagType(name="detect_good", bit=64, settable=True),
    FlagType(name="sanctuary", bit=128, settable=True),
    FlagType(name="faerie_fire", bit=256, settable=True),
    FlagType(name="infrared", bit=512, settable=True),
    FlagType(name="curse", bit=1024, settable=True),
    FlagType(name="poison", bit=4096, settable=True),
    FlagType(name="protect_evil", bit=8192, settable=True),
    FlagType(name="protect_good", bit=16384, settable=True),
    FlagType(name="sneak", bit=32768, settable=True),
    FlagType(name="hide", bit=65536, settable=True),
    FlagType(name="sleep", bit=131072, settable=True),
    FlagType(name="charm", bit=262144, settable=True),
    FlagType(name="flying", bit=524288, settable=True),
    FlagType(name="pass_door", bit=1048576, settable=True),
    FlagType(name="haste", bit=2097152, settable=True),
    FlagType(name="calm", bit=4194304, settable=True),
    FlagType(name="plague", bit=8388608, settable=True),
    FlagType(name="weaken", bit=16777216, settable=True),
    FlagType(name="dark_vision", bit=33554432, settable=True),
    FlagType(name="berserk", bit=67108864, settable=True),
    FlagType(name="swim", bit=134217728, settable=True),
    FlagType(name="regeneration", bit=268435456, settable=True),
    FlagType(name="slow", bit=536870912, settable=True),
)

# off_flags, tables.c
OFF_FLAGS = (
    FlagType(name="area_attack", bit=1, settable=True),
    FlagType(name="backstab", bit=2, settable=True),
    FlagType(name="bash", bit=4, settable=True),
    FlagType(name="berserk", bit=8, settable=True),
    FlagType(name="disarm", bit=16, settable=True),
    FlagType(name="dodge", bit=32, settable=True),
    FlagType(name="fade", bit=64, settable=True),
    FlagType(name="fast", bit=128, settable=True),
    FlagType(name="kick", bit=256, settable=True),
    FlagType(name="dirt_kick", bit=512, settable=True),
    FlagType(name="parry", bit=1024, settable=True),
    FlagType(name="rescue", bit=2048, settable=True),
    FlagType(name="tail", bit=4096, settable=True),
    FlagType(name="trip", bit=8192, settable=True),
    FlagType(name="crush", bit=16384, settable=True),
    FlagType(name="assist_all", bit=32768, settable=True),
    FlagType(name="assist_align", bit=65536, settable=True),
    FlagType(name="assist_race", bit=131072, settable=True),
    FlagType(name="assist_players", bit=262144, settable=True),
    FlagType(name="assist_guard", bit=524288, settable=True),
    FlagType(name="assist_vnum", bit=1048576, settable=True),
)

# imm_flags, tables.c
IMM_FLAGS = (
    FlagType(name="summon", bit=1, settable=True),
    FlagType(name="charm", bit=2, settable=True),
    FlagType(name="magic", bit=4, settable=True),
    FlagType(name="weapon", bit=8, settable=True),
    FlagType(name="bash", bit=16, settable=True),
    FlagType(name="pierce", bit=32, settable=True),
    FlagType(name="slash", bit=64, settable=True),
    FlagType(name="fire", bit=128, settable=True),
    FlagType(name="cold", bit=256, settable=True),
    FlagType(name="lightning", bit=512, settable=True),
    FlagType(name="acid", bit=1024, settable=True),
    FlagType(name="poison", bit=2048, settable=True),
    FlagType(name="negative", bit=4096, settable=True),
    FlagType(name="holy", bit=8192, settable=True),
    FlagType(name="energy", bit=16384, settable=True),
    FlagType(name="mental", bit=32768, settable=True),
    FlagType(name="disease", bit=65536, settable=True),
    FlagType(name="drowning", bit=131072, settable=True),
    FlagType(name="light", bit=262144, settable=True),
    FlagType(name="sound", bit=524288, settable=True),
    FlagType(name="wood", bit=8388608, settable=True),
    FlagType(name="silver", bit=16777216, settable=True),
    FlagType(name="iron", bit=33554432, settable=True),
)

# plr_flags, tables.c
PLR_FLAGS = (
    FlagType(name="npc", bit=1, settable=False),
    FlagType(name="autoassist", bit=4, settable=False),
    FlagType(name="autoexit", bit=8, settable=False),
    FlagType(name="autoloot", bit=16, settable=False),
    FlagType(name="autosac", bit=32, settable=False),
    FlagType(name="autogold", bit=64, settable=False),
    FlagType(name="autosplit", bit=128, settable=False),
    FlagType(name="holylight", bit=8192, settable=False),
    FlagType(name="can_loot", bit=32768, settable=False),
    FlagType(name="nosummon", bit=65536, settable=False),
    FlagType(name="nofollow", bit=131072, settable=False),
    FlagType(name="colour", bit=524288, settable=False),
    FlagType(name="permit", bit=1048576, settable=True),
    FlagType(name="log", bit=4194304, settable=False),
    FlagType(name="deny", bit=8388608, settable=False),
    FlagType(name="freeze", bit=16777216, settable=False),
    FlagType(name="thief", bit=33554432, settable=False),
    FlagType(name="killer", bit=67108864, settable=False),
)

# form_flags, tables.c
FORM_FLAGS = (
    FlagType(name="edible", bit=1, settable=True),
    FlagType(name="poison", bit=2, settable=True),
    FlagType(name="magical", bit=4, settable=True),
    FlagType(name="instant_decay", bit=8, settable=True),
    FlagType(name="other", bit=16, settable=True),
    FlagType(name="animal", bit=64, settable=True),
    FlagType(name="sentient", bit=128, settable=True),
    FlagType(name="undead", bit=256, settable=True),
    FlagType(name="construct", bit=512, settable=True),
    FlagType(name="mist", bit=1024, settable=True),
    FlagType(name="intangible", bit=2048, settable=True),
    FlagType(name="biped", bit=4096, settable=True),
    FlagType(name="centaur", bit=8192, settable=True),
    FlagType(name="insect", bit=16384, settable=True),
    FlagType(name="spider", bit=32768, settable=True),
    FlagType(name="crustacean", bit=65536, settable=True),
    FlagType(name="worm", bit=131072, settable=True),
    FlagType(name="blob", bit=262144, settable=True),
    FlagType(name="mammal", bit=2097152, settable=True),
    FlagType(name="bird", bit=4194304, settable=True),
    FlagType(name="reptile", bit=8388608, settable=True),
    FlagType(name="snake", bit=16777216, settable=True),
    FlagType(name="dragon", bit=33554432, settable=True),
    FlagType(name="amphibian", bit=67108864, settable=True),
    FlagType(name="fish", bit=134217728, settable=True),
    FlagType(name="cold_blood", bit=268435456, settable=True),
)

# part_flags, tables.c
PART_FLAGS = (
    FlagType(name="head", bit=1, settable=True),
    FlagType(name="arms", bit=2, settable=True),
    FlagType(name="legs", bit=4, settable=True),
    FlagType(name="heart", bit=8, settable=True),
    FlagType(name="brains", bit=16, settable=True),
    FlagType(name="guts", bit=32, settable=True),
    FlagType(name="hands", bit=64, settable=True),
    FlagType(name="feet", bit=128, settable=True),
    FlagType(name="fingers", bit=256, settable=True),
    FlagType(name="ear", bit=512, settable=True),
    FlagType(name="eye", bit=1024, settable=True),
    FlagType(name="long_tongue", bit=2048, settable=True),
    FlagType(name="eyestalks", bit=4096, settable=True),
    FlagType(name="tentacles", bit=8192, settable=True),
    FlagType(name="fins", bit=16384, settable=True),
    FlagType(name="wings", bit=32768, settable=True),
    FlagType(name="tail", bit=65536, settable=True),
    FlagType(name="claws", bit=1048576, settable=True),
    FlagType(name="fangs", bit=2097152, settable=True),
    FlagType(name="horns", bit=4194304, settable=True),
    FlagType(name="scales", bit=8388608, settable=True),
    FlagType(name="tusks", bit=16777216, settable=True),
)

# comm_flags, tables.c
COMM_FLAGS = (
    FlagType(name="quiet", bit=1, settable=True),
    FlagType(name="deaf", bit=2, settable=True),
    FlagType(name="nowiz", bit=4, settable=True),
    FlagType(name="noclangossip", bit=8, settable=True),
    FlagType(name="nogossip", bit=16, settable=True),
    FlagType(name="noquestion", bit=32, settable=True),
    FlagType(name="nomusic", bit=64, settable=True),
    FlagType(name="noclan", bit=128, settable=True),
    FlagType(name="noquote", bit=256, settable=True),
    FlagType(name="shoutsoff", bit=512, settable=True),
    FlagType(name="compact", bit=2048, settable=True),
    FlagType(name="brief", bit=4096, settable=True),
    FlagType(name="prompt", bit=8192, settable=True),
    FlagType(name="combine", bit=16384, settable=True),
    FlagType(name="telnet_ga", bit=32768, settable=True),
    FlagType(name="show_affects", bit=65536, settable=True),
    FlagType(name="nograts", bit=131072, settable=True),
    FlagType(name="noemote", bit=524288, settable=False),
    FlagType(name="noshout", bit=1048576, settable=False),
    FlagType(name="notell", bit=2097152, settable=False),
    FlagType(name="nochannels", bit=4194304, settable=False),
    FlagType(name="snoop_proof", bit=16777216, settable=False),
    FlagType(name="afk", bit=33554432, settable=True),
)

# area_flags, tables.c
AREA_FLAGS = (
    FlagType(name="none", bit=0, settable=False),
    FlagType(name="changed", bit=1, settable=True),
    FlagType(name="added", bit=2, settable=True),
    FlagType(name="loading", bit=4, settable=False),
)

# sex_flags, tables.c
SEX_FLAGS = (
    FlagType(name="male", bit=1, settable=True),
    FlagType(name="female", bit=2, settable=True),
    FlagType(name="neutral", bit=0, settable=True),
    FlagType(name="random", bit=3, settable=True),
    FlagType(name="none", bit=0, settable=True),
)

# exit_flags, tables.c
EXIT_FLAGS = (
    FlagType(name="door", bit=1, settable=True),
    FlagType(name="closed", bit=2, settable=True),
    FlagType(name="locked", bit=4, settable=True),
    FlagType(name="pickproof", bit=32, settable=True),
    FlagType(name="nopass", bit=64, settable=True),
    FlagType(name="easy", bit=128, settable=True),
    FlagType(name="hard", bit=256, settable=True),
    FlagType(name="infuriating", bit=512, settable=True),
    FlagType(name="noclose", bit=1024, settable=True),
    FlagType(name="nolock", bit=2048, settable=True),
)

# door_resets, tables.c
DOOR_RESETS = (
    FlagType(name="open and unlocked", bit=0, settable=True),
    FlagType(name="closed and unlocked", bit=1, settable=True),
    FlagType(name="closed and locked", bit=2, settable=True),
)

# room_flags, tables.c
ROOM_FLAGS = (
    FlagType(name="dark", bit=1, settable=True),
    FlagType(name="no_mob", bit=4, settable=True),
    FlagType(name="indoors", bit=8, settable=True),
    FlagType(name="private", bit=512, settable=True),
    FlagType(name="safe", bit=1024, settable=True),
    FlagType(name="solitary", bit=2048, settable=True),
    FlagType(name="pet_shop", bit=4096, settable=True),
    FlagType(name="no_recall", bit=8192, settable=True),
    FlagType(name="imp_only", bit=16384, settable=True),
    FlagType(name="gods_only", bit=32768, settable=True),
    FlagType(name="heroes_only", bit=65536, settable=True),
    FlagType(name="newbies_only", bit=131072, settable=True),
    FlagType(name="law", bit=262144, settable=True),
    FlagType(name="nowhere", bit=524288, settable=True),
)

# sector_flags, tables.c
SECTOR_FLAGS = (
    FlagType(name="inside", bit=0, settable=True),
    FlagType(name="city", bit=1, settable=True),
    FlagType(name="field", bit=2, settable=True),
    FlagType(name="forest", bit=3, settable=True),
    FlagType(name="hills", bit=4, settable=True),
    FlagType(name="mountain", bit=5, settable=True),
    FlagType(name="swim", bit=6, settable=True),
    FlagType(name="noswim", bit=7, settable=True),
    FlagType(name="unused", bit=8, settable=True),
    FlagType(name="air", bit=9, settable=True),
    FlagType(name="desert", bit=10, settable=True),
)

# type_flags, tables.c
TYPE_FLAGS = (
    FlagType(name="light", bit=1, settable=True),
    FlagType(name="scroll", bit=2, settable=True),
    FlagType(name="wand", bit=3, settable=True),
    FlagType(name="staff", bit=4, settable=True),
    FlagType(name="weapon", bit=5, settable=True),
    FlagType(name="treasure", bit=8, settable=True),
    FlagType(name="armor", bit=9, settable=True),
    FlagType(name="potion", bit=10, settable=True),
    FlagType(name="furniture", bit=12, settable=True),
    FlagType(name="trash", bit=13, settable=True),
    FlagType(name="container", bit=15, settable=True),
    FlagType(name="drinkcontainer", bit=17, settable=True),
    FlagType(name="key", bit=18, settable=True),
    FlagType(name="food", bit=19, settable=True),
    FlagType(name="money", bit=20, settable=True),
    FlagType(name="boat", bit=22, settable=True),
    FlagType(name="npccorpse", bit=23, settable=True),
    FlagType(name="pc corpse", bit=24, settable=False),
    FlagType(name="fountain", bit=25, settable=True),
    FlagType(name="pill", bit=26, settable=True),
    FlagType(name="protect", bit=27, settable=True),
    FlagType(name="map", bit=28, settable=True),
    FlagType(name="portal", bit=29, settable=True),
    FlagType(name="warpstone", bit=30, settable=True),
    FlagType(name="roomkey", bit=31, settable=True),
    FlagType(name="gem", bit=32, settable=True),
    FlagType(name="jewelry", bit=33, settable=True),
    FlagType(name="jukebox", bit=34, settable=True),
)

# extra_flags, tables.c
EXTRA_FLAGS = (
    FlagType(name="glow", bit=1, settable=True),
    FlagType(name="hum", bit=2, settable=True),
    FlagType(name="dark", bit=4, settable=True),
    FlagType(name="lock", bit=8, settable=True),
    FlagType(name="evil", bit=16, settable=True),
    FlagType(name="invis", bit=32, settable=True),
    FlagType(name="magic", bit=64, settable=True),
    FlagType(name="nodrop", bit=128, settable=True),
    FlagType(name="bless", bit=256, settable=True),
    FlagType(name="antigood", bit=512, settable=True),
    FlagType(name="antievil", bit=1024, settable=True),
    FlagType(name="antineutral", bit=2048, settable=True),
    FlagType(name="noremove", bit=4096, settable=True),
    FlagType(name="inventory", bit=8192, settable=True),
    FlagType(name="nopurge", bit=16384, settable=True),
    FlagType(name="rotdeath", bit=32768, settable=True),
    FlagType(name="visdeath", bit=65536, settable=True),
    FlagType(name="nonmetal", bit=262144, settable=True),
    FlagType(name="meltdrop", bit=1048576, settable=True),
    FlagType(name="hadtimer", bit=2097152, settable=True),
    FlagType(name="sellextract", bit=4194304, settable=True),
    FlagType(name="burnproof", bit=16777216, settable=True),
    FlagType(name="nouncurse", bit=33554432, settable=True),
)

# wear_flags, tables.c
WEAR_FLAGS = (
    FlagType(name="take", bit=1, settable=True),
    FlagType(name="finger", bit=2, settable=True),
    FlagType(name="neck", bit=4, settable=True),
    FlagType(name="body", bit=8, settable=True),
    FlagType(name="head", bit=16, settable=True),
    FlagType(name="legs", bit=32, settable=True),
    FlagType(name="feet", bit=64, settable=True),
    FlagType(name="hands", bit=128, settable=True),
    FlagType(name="arms", bit=256, settable=True),
    FlagType(name="shield", bit=512, settable=True),
    FlagType(name="about", bit=1024, settable=True),
    FlagType(name="waist", bit=2048, settable=True),
    FlagType(name="wrist", bit=4096, settable=True),
    FlagType(name="wield", bit=8192, settable=True),
    FlagType(name="hold", bit=16384, settable=True),
    FlagType(name="nosac", bit=32768, settable=True),
    FlagType(name="wearfloat", bit=65536, settable=True),
)

# apply_flags, tables.c
APPLY_FLAGS = (
    FlagType(name="none", bit=0, settable=True),
    FlagType(name="strength", bit=1, settable=True),
    FlagType(name="dexterity", bit=2, settable=True),
    FlagType(name="intelligence", bit=3, settable=True),
    FlagType(name="wisdom", bit=4, settable=True),
    FlagType(name="constitution", bit=5, settable=True),
    FlagType(name="sex", bit=6, settable=True),
    FlagType(name="class", bit=7, settable=True),
    FlagType(name="level", bit=8, settable=True),
    FlagType(name="age", bit=9, settable=True),
    FlagType(name="height", bit=10, settable=True),
    FlagType(name="weight", bit=11, settable=True),
    FlagType(name="mana", bit=12, settable=True),
    FlagType(name="hp", bit=13, settable=True),
    FlagType(name="move", bit=14, settable=True),
    FlagType(name="gold", bit=15, settable=True),
    FlagType(name="experience", bit=16, settable=True),
    FlagType(name="ac", bit=17, settable=True),
    FlagType(name="hitroll", bit=18, settable=True),
    FlagType(name="damroll", bit=19, settable=True),
    FlagType(name="saves", bit=20, settable=True),
    FlagType(name="savingpara", bit=20, settable=True),
    FlagType(name="savingrod", bit=21, settable=True),
    FlagType(name="savingpetri", bit=22, settable=True),
    FlagType(name="savingbreath", bit=23, settable=True),
    FlagType(name="savingspell", bit=24, settable=True),
    FlagType(name="spellaffect", bit=25, settable=False),
)

# wear_loc_strings, tables.c
WEAR_LOC_STRINGS = (
    FlagType(name="in the inventory", bit=-1, settable=True),
    FlagType(name="as a light", bit=0, settable=True),
    FlagType(name="on the left finger", bit=1, settable=True),
    FlagType(name="on the right finger", bit=2, settable=True),
    FlagType(name="around the neck (1)", bit=3, settable=True),
    FlagType(name="around the neck (2)", bit=4, settable=True),
    FlagType(name="on the body", bit=5, settable=True),
    FlagType(name="over the head", bit=6, settable=True),
    FlagType(name="on the legs", bit=7, settable=True),
    FlagType(name="on the feet", bit=8, settable=True),
    FlagType(name="on the hands", bit=9, settable=True),
    FlagType(name="on the arms", bit=10, settable=True),
    FlagType(name="as a shield", bit=11, settable=True),
    FlagType(name="about the shoulders", bit=12, settable=True),
    FlagType(name="around the waist", bit=13, settable=True),
    FlagType(name="on the left wrist", bit=14, settable=True),
    FlagType(name="on the right wrist", bit=15, settable=True),
    FlagType(name="wielded", bit=16, settable=True),
    FlagType(name="held in the hands", bit=17, settable=True),
    FlagType(name="floating nearby", bit=18, settable=True),
)

# wear_loc_flags, tables.c
WEAR_LOC_FLAGS = (
    FlagType(name="none", bit=-1, settable=True),
    FlagType(name="light", bit=0, settable=True),
    FlagType(name="lfinger", bit=1, settable=True),
    FlagType(name="rfinger", bit=2, settable=True),
    FlagType(name="neck1", bit=3, settable=True),
    FlagType(name="neck2", bit=4, settable=True),
    FlagType(name="body", bit=5, settable=True),
    FlagType(name="head", bit=6, settable=True),
    FlagType(name="legs", bit=7, settable=True),
    FlagType(name="feet", bit=8, settable=True),
    FlagType(name="hands", bit=9, settable=True),
    FlagType(name="arms", bit=10, settable=True),
    FlagType(name="shield", bit=11, settable=True),
    FlagType(name="about", bit=12, settable=True),
    FlagType(name="waist", bit=13, settable=True),
    FlagType(name="lwrist", bit=14, settable=True),
    FlagType(name="rwrist", bit=15, settable=True),
    FlagType(name="wielded", bit=16, settable=True),
    FlagType(name="hold", bit=17, settable=True),
    FlagType(name="floating", bit=18, settable=True),
)

# container_flags, tables.c
CONTAINER_FLAGS = (
    FlagType(name="closeable", bit=1, settable=True),
    FlagType(name="pickproof", bit=2, settable=True),
    FlagType(name="closed", bit=4, settable=True),
    FlagType(name="locked", bit=8, settable=True),
    FlagType(name="puton", bit=16, settable=True),
)

# ac_type, tables.c
AC_TYPE = (
    FlagType(name="pierce", bit=0, settable=True),
    FlagType(name="bash", bit=1, settable=True),
    FlagType(name="slash", bit=2, settable=True),
    FlagType(name="exotic", bit=3, settable=True),
)

# size_flags, tables.c
SIZE_FLAGS = (
    FlagType(name="tiny", bit=0, settable=True),
    FlagType(name="small", bit=1, settable=True),
    FlagType(name="medium", bit=2, settable=True),
    FlagType(name="large", bit=3, settable=True),
    FlagType(name="huge", bit=4, settable=True),
    FlagType(name="giant", bit=5, settable=True),
)

# weapon_class, tables.c
WEAPON_CLASS = (
    FlagType(name="exotic", bit=0, settable=True),
    FlagType(name="sword", bit=1, settable=True),
    FlagType(name="dagger", bit=2, settable=True),
    FlagType(name="spear", bit=3, settable=True),
    FlagType(name="mace", bit=4, settable=True),
    FlagType(name="axe", bit=5, settable=True),
    FlagType(name="flail", bit=6, settable=True),
    FlagType(name="whip", bit=7, settable=True),
    FlagType(name="polearm", bit=8, settable=True),
)

# weapon_type2, tables.c
WEAPON_TYPE2 = (
    FlagType(name="flaming", bit=1, settable=True),
    FlagType(name="frost", bit=2, settable=True),
    FlagType(name="vampiric", bit=4, settable=True),
    FlagType(name="sharp", bit=8, settable=True),
    FlagType(name="vorpal", bit=16, settable=True),
    FlagType(name="twohands", bit=32, settable=True),
    FlagType(name="shocking", bit=64, settable=True),
    FlagType(name="poison", bit=128, settable=True),
)

# res_flags, tables.c
RES_FLAGS = (
    FlagType(name="summon", bit=1, settable=True),
    FlagType(name="charm", bit=2, settable=True),
    FlagType(name="magic", bit=4, settable=True),
    FlagType(name="weapon", bit=8, settable=True),
    FlagType(name="bash", bit=16, settable=True),
    FlagType(name="pierce", bit=32, settable=True),
    FlagType(name="slash", bit=64, settable=True),
    FlagType(name="fire", bit=128, settable=True),
    FlagType(name="cold", bit=256, settable=True),
    FlagType(name="lightning", bit=512, settable=True),
    FlagType(name="acid", bit=1024, settable=True),
    FlagType(name="poison", bit=2048, settable=True),
    FlagType(name="negative", bit=4096, settable=True),
    FlagType(name="holy", bit=8192, settable=True),
    FlagType(name="energy", bit=16384, settable=True),
    FlagType(name="mental", bit=32768, settable=True),
    FlagType(name="disease", bit=65536, settable=True),
    FlagType(name="drowning", bit=131072, settable=True),
    FlagType(name="light", bit=262144, settable=True),
    FlagType(name="sound", bit=524288, settable=True),
    FlagType(name="wood", bit=8388608, settable=True),
    FlagType(name="silver", bit=16777216, settable=True),
    FlagType(name="iron", bit=33554432, settable=True),
)

# vuln_flags, tables.c
VULN_FLAGS = (
    FlagType(name="summon", bit=1, settable=True),
    FlagType(name="charm", bit=2, settable=True),
    FlagType(name="magic", bit=4, settable=True),
    FlagType(name="weapon", bit=8, settable=True),
    FlagType(name="bash", bit=16, settable=True),
    FlagType(name="pierce", bit=32, settable=True),
    FlagType(name="slash", bit=64, settable=True),
    FlagType(name="fire", bit=128, settable=True),
    FlagType(name="cold", bit=256, settable=True),
    FlagType(name="lightning", bit=512, settable=True),
    FlagType(name="acid", bit=1024, settable=True),
    FlagType(name="poison", bit=2048, settable=True),
    FlagType(name="negative", bit=4096, settable=True),
    FlagType(name="holy", bit=8192, settable=True),
    FlagType(name="energy", bit=16384, settable=True),
    FlagType(name="mental", bit=32768, settable=True),
    FlagType(name="disease", bit=65536, settable=True),
    FlagType(name="drowning", bit=131072, settable=True),
    FlagType(name="light", bit=262144, settable=True),
    FlagType(name="sound", bit=524288, settable=True),
    FlagType(name="wood", bit=8388608, settable=True),
    FlagType(name="silver", bit=16777216, settable=True),
    FlagType(name="iron", bit=33554432, settable=True),
)

# position_flags, tables.c
POSITION_FLAGS = (
    FlagType(name="dead", bit=0, settable=False),
    FlagType(name="mortal", bit=1, settable=False),
    FlagType(name="incap", bit=2, settable=False),
    FlagType(name="stunned", bit=3, settable=False),
    FlagType(name="sleeping", bit=4, settable=True),
    FlagType(name="resting", bit=5, settable=True),
    FlagType(name="sitting", bit=6, settable=True),
    FlagType(name="fighting", bit=7, settable=False),
    FlagType(name="standing", bit=8, settable=True),
)

# portal_flags, tables.c
PORTAL_FLAGS = (
    FlagType(name="normal_exit", bit=1, settable=True),
    FlagType(name="no_curse", bit=2, settable=True),
    FlagType(name="go_with", bit=4, settable=True),
    FlagType(name="buggy", bit=8, settable=True),
    FlagType(name="random", bit=16, settable=True),
)

# furniture_flags, tables.c
FURNITURE_FLAGS = (
    FlagType(name="stand_at", bit=1, settable=True),
    FlagType(name="stand_on", bit=2, settable=True),
    FlagType(name="stand_in", bit=4, settable=True),
    FlagType(name="sit_at", bit=8, settable=True),
    FlagType(name="sit_on", bit=16, settable=True),
    FlagType(name="sit_in", bit=32, settable=True),
    FlagType(name="rest_at", bit=64, settable=True),
    FlagType(name="rest_on", bit=128, settable=True),
    FlagType(name="rest_in", bit=256, settable=True),
    FlagType(name="sleep_at", bit=512, settable=True),
    FlagType(name="sleep_on", bit=1024, settable=True),
    FlagType(name="sleep_in", bit=2048, settable=True),
    FlagType(name="put_at", bit=4096, settable=True),
    FlagType(name="put_on", bit=8192, settable=True),
    FlagType(name="put_in", bit=16384, settable=True),
    FlagType(name="put_inside", bit=32768, settable=True),
)

# apply_types, tables.c
APPLY_TYPES = (
    FlagType(name="affects", bit=0, settable=True),
    FlagType(name="object", bit=1, settable=True),
    FlagType(name="immune", bit=2, settable=True),
    FlagType(name="resist", bit=3, settable=True),
    FlagType(name="vuln", bit=4, settable=True),
    FlagType(name="weapon", bit=5, settable=True),
)
