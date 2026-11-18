/* worldcheck: boot the C game's world and print it, for charm_tools port world (abraidotti/charm#25).
 *
 * Linked against the game's object files, with comm.c compiled as -Dmain=game_main, so this is the game's real
 * boot_db, reset_room, create_mobile and the rest. The clock and the seed are fixed, so a boot is repeatable.
 *
 * Usage: worldcheck SEED TIME UPDATES (run from the area directory, like the game)
 *   SEED     goes to init_mm through CHARM_SEED
 *   TIME     is current_time at boot (it sets the game's hour and month, and so the weather draw)
 *   UPDATES  is how many more area_update calls to run after boot, each followed by another dump
 *
 * Output: "dump N" then the world after boot (N = 0) and after each extra area_update. The format is plain lines,
 * one thing per line, the same in game/charm's world dump, so the two can be compared with diff. The game's log
 * (bug() and log_f lines) goes to stderr.
 *
 * Part of charm_tools (MIT, tools/LICENSE). It calls the game's code but contains none of it.
 */
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include "merc.h"

void boot_db (void);   /* db.c */
void area_update (void);   /* db.c */
extern int mobile_count;   /* db.c */

#define MAX_VNUM 32768

/* Strings on one line: backslash, newline and carriage return escaped. */
static void str (const char *s)
{
    putchar ('"');
    for (; s != NULL && *s; s++)
    {
        if (*s == '\\') fputs ("\\\\", stdout);
        else if (*s == '\n') fputs ("\\n", stdout);
        else if (*s == '\r') fputs ("\\r", stdout);
        else if (*s == '"') fputs ("\\\"", stdout);
        else putchar (*s);
    }
    putchar ('"');
}

static int char_index (CHAR_DATA *ch)
{
    CHAR_DATA *c;
    int i = 0;
    for (c = char_list; c != NULL; c = c->next, i++)
        if (c == ch) return i;
    return -1;
}

static int obj_index (OBJ_DATA *obj)
{
    OBJ_DATA *o;
    int i = 0;
    for (o = object_list; o != NULL; o = o->next, i++)
        if (o == obj) return i;
    return -1;
}

static void affects (const char *tag, AFFECT_DATA *paf)
{
    for (; paf != NULL; paf = paf->next)
        printf ("  %s where=%d type=%d level=%d duration=%d location=%d modifier=%d bits=%d\n", tag, paf->where,
                paf->type, paf->level, paf->duration, paf->location, paf->modifier, paf->bitvector);
}

static void obj_list (const char *tag, OBJ_DATA *obj)
{
    printf (" %s=", tag);
    for (; obj != NULL; obj = obj->next_content)
        printf ("%d%s", obj_index (obj), obj->next_content ? "," : "");
}

static void prototypes (void)
{
    AREA_DATA *pArea;
    int vnum, i;

    for (pArea = area_first, i = 0; pArea != NULL; pArea = pArea->next, i++)
    {
        printf ("area %d min=%d max=%d ", i, pArea->min_vnum, pArea->max_vnum);
        str (pArea->name);
        printf ("\n");
    }

    for (vnum = 0; vnum < MAX_VNUM; vnum++)
    {
        MOB_INDEX_DATA *m = get_mob_index (vnum);
        MPROG_LIST *mp;
        if (m == NULL) continue;
        printf ("mobindex %d act=%ld aff=%ld off=%ld imm=%ld res=%ld vuln=%ld form=%ld parts=%ld race=%d size=%d "
                "sex=%d pos=%d,%d dam_type=%d wealth=%ld level=%d hitroll=%d align=%d group=%d hit=%d,%d,%d "
                "mana=%d,%d,%d damage=%d,%d,%d ac=%d,%d,%d,%d mprog_flags=%ld new=%d shop=%d spec=%s ",
                vnum, m->act, m->affected_by, m->off_flags, m->imm_flags, m->res_flags, m->vuln_flags, m->form,
                m->parts, m->race, m->size, m->sex, m->start_pos, m->default_pos, m->dam_type, m->wealth, m->level,
                m->hitroll, m->alignment, m->group, m->hit[0], m->hit[1], m->hit[2], m->mana[0], m->mana[1],
                m->mana[2], m->damage[0], m->damage[1], m->damage[2], m->ac[0], m->ac[1], m->ac[2], m->ac[3],
                m->mprog_flags, m->new_format, m->pShop != NULL, m->spec_fun ? spec_name (m->spec_fun) : "-");
        str (m->material); putchar (' ');
        str (m->player_name); putchar (' ');
        str (m->short_descr); putchar (' ');
        str (m->long_descr); putchar (' ');
        str (m->description);
        printf ("\n");
        for (mp = m->mprogs; mp != NULL; mp = mp->next)
        {
            printf ("  mprog trig=%d vnum=%d ", mp->trig_type, mp->vnum);
            str (mp->trig_phrase);
            printf ("\n");
        }
    }

    for (vnum = 0; vnum < MAX_VNUM; vnum++)
    {
        OBJ_INDEX_DATA *o = get_obj_index (vnum);
        EXTRA_DESCR_DATA *ed;
        if (o == NULL) continue;
        printf ("objindex %d type=%d extra=%d wear=%d values=%d,%d,%d,%d,%d level=%d weight=%d cost=%d "
                "condition=%d new=%d ", vnum, o->item_type, o->extra_flags, o->wear_flags, o->value[0], o->value[1],
                o->value[2], o->value[3], o->value[4], o->level, o->weight, o->cost, o->condition, o->new_format);
        str (o->material); putchar (' ');
        str (o->name); putchar (' ');
        str (o->short_descr); putchar (' ');
        str (o->description);
        printf ("\n");
        affects ("aff", o->affected);
        for (ed = o->extra_descr; ed != NULL; ed = ed->next)
        {
            printf ("  ed ");
            str (ed->keyword);
            printf ("\n");
        }
    }
}

static void state (int n)
{
    AREA_DATA *pArea;
    CHAR_DATA *ch;
    OBJ_DATA *obj;
    int vnum, i, d;

    printf ("dump %d\n", n);
    printf ("time hour=%d day=%d month=%d year=%d\n", time_info.hour, time_info.day, time_info.month,
            time_info.year);
    printf ("weather mmhg=%d change=%d sky=%d sunlight=%d\n", weather_info.mmhg, weather_info.change,
            weather_info.sky, weather_info.sunlight);
    for (pArea = area_first, i = 0; pArea != NULL; pArea = pArea->next, i++)
        printf ("areastate %d age=%d nplayer=%d empty=%d\n", i, pArea->age, pArea->nplayer, pArea->empty);

    for (vnum = 0; vnum < MAX_VNUM; vnum++)
    {
        ROOM_INDEX_DATA *r = get_room_index (vnum);
        if (r == NULL) continue;
        printf ("room %d light=%d flags=%d", vnum, r->light, r->room_flags);
        printf (" people=");
        for (ch = r->people; ch != NULL; ch = ch->next_in_room)
            printf ("%d%s", char_index (ch), ch->next_in_room ? "," : "");
        obj_list ("contents", r->contents);
        printf ("\n");
        for (d = 0; d < MAX_DIR; d++)
        {
            EXIT_DATA *e = r->exit[d];
            if (e == NULL) continue;
            printf ("  exit %d to=%d info=%d rs=%d key=%d orig=%d\n", d, e->u1.to_room ? e->u1.to_room->vnum : -1,
                    e->exit_info, e->rs_flags, e->key, e->orig_door);
        }
    }

    for (vnum = 0; vnum < MAX_VNUM; vnum++)
    {
        MOB_INDEX_DATA *m = get_mob_index (vnum);
        OBJ_INDEX_DATA *o = get_obj_index (vnum);
        if (m != NULL) printf ("mobcount %d %d\n", vnum, m->count);
        if (o != NULL) printf ("objcount %d %d\n", vnum, o->count);
    }

    for (ch = char_list, i = 0; ch != NULL; ch = ch->next, i++)
    {
        printf ("char %d vnum=%d id=%ld room=%d level=%d hit=%d/%d mana=%d/%d move=%d/%d gold=%ld silver=%ld "
                "sex=%d race=%d size=%d dam_type=%d act=%ld comm=%ld aff=%ld off=%ld imm=%ld res=%ld vuln=%ld "
                "form=%ld parts=%ld pos=%d,%d,%d align=%d hitroll=%d damroll=%d saves=%d group=%d "
                "armor=%d,%d,%d,%d damage=%d,%d,%d perm=%d,%d,%d,%d,%d mod=%d,%d,%d,%d,%d carry=%d,%d ",
                i, ch->pIndexData ? ch->pIndexData->vnum : -1, ch->id, ch->in_room ? ch->in_room->vnum : -1,
                ch->level, ch->hit, ch->max_hit, ch->mana, ch->max_mana, ch->move, ch->max_move, ch->gold,
                ch->silver, ch->sex, ch->race, ch->size, ch->dam_type, ch->act, ch->comm, ch->affected_by,
                ch->off_flags, ch->imm_flags, ch->res_flags, ch->vuln_flags, ch->form, ch->parts, ch->position,
                ch->start_pos, ch->default_pos, ch->alignment, ch->hitroll, ch->damroll, ch->saving_throw,
                ch->group, ch->armor[0], ch->armor[1], ch->armor[2], ch->armor[3], ch->damage[0], ch->damage[1],
                ch->damage[2], ch->perm_stat[0], ch->perm_stat[1], ch->perm_stat[2], ch->perm_stat[3],
                ch->perm_stat[4], ch->mod_stat[0], ch->mod_stat[1], ch->mod_stat[2], ch->mod_stat[3],
                ch->mod_stat[4], ch->carry_number, ch->carry_weight);
        str (ch->material); putchar (' ');
        str (ch->name);
        obj_list ("carrying", ch->carrying);
        printf ("\n");
        affects ("aff", ch->affected);
    }

    for (obj = object_list, i = 0; obj != NULL; obj = obj->next, i++)
    {
        printf ("obj %d vnum=%d ", i, obj->pIndexData->vnum);
        if (obj->in_room) printf ("in=room:%d", obj->in_room->vnum);
        else if (obj->carried_by) printf ("in=char:%d", char_index (obj->carried_by));
        else if (obj->in_obj) printf ("in=obj:%d", obj_index (obj->in_obj));
        else printf ("in=-");
        printf (" wear=%d type=%d level=%d cost=%d timer=%d values=%d,%d,%d,%d,%d extra=%d wearflags=%d "
                "weight=%d condition=%d enchanted=%d ", obj->wear_loc, obj->item_type, obj->level, obj->cost,
                obj->timer, obj->value[0], obj->value[1], obj->value[2], obj->value[3], obj->value[4],
                obj->extra_flags, obj->wear_flags, obj->weight, obj->condition, obj->enchanted);
        str (obj->material); putchar (' ');
        str (obj->name);
        obj_list ("contains", obj->contains);
        printf ("\n");
        affects ("aff", obj->affected);
    }

    printf ("count mobiles=%d\n", mobile_count);
    {
        /* Three draws, so a different number of draws during boot or resets shows. They're part of the run: the
         * Python dump draws them too. Sequenced, because argument order isn't. */
        long a = number_mm (), b = number_mm (), c = number_mm ();
        printf ("rng %ld %ld %ld\n", a, b, c);
    }
}

int main (int argc, char **argv)
{
    int updates, n;

    if (argc != 4)
    {
        fprintf (stderr, "usage: %s SEED TIME UPDATES\n", argv[0]);
        return 2;
    }
    setenv ("CHARM_SEED", argv[1], 1);
    current_time = (time_t) atol (argv[2]);
    updates = atoi (argv[3]);

    boot_db ();
    prototypes ();
    state (0);
    for (n = 1; n <= updates; n++)
    {
        area_update ();
        state (n);
    }
    return 0;
}
