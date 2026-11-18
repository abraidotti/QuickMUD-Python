/* cryptcheck: glibc's crypt() on the cases charm_tools port crypt sends, for game/charm/core/crypt.py (#30).
 *
 * Reads lines "KEYHEX SALT" on stdin (the key hex-encoded, so any byte but NUL can be tested) and prints
 * crypt(key, salt) for each, one per line: the same call the C game makes in nanny and do_password.
 *
 * Part of charm_tools (MIT, tools/LICENSE). It calls the C library; it contains none of the game.
 */
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <crypt.h>

int main (void)
{
    char line[1024], hex[1024], salt[16], key[512];
    while (fgets (line, sizeof (line), stdin))
    {
        int i, n;
        const char *out;
        if (sscanf (line, "%1023s %15s", hex, salt) != 2)
        {
            if (sscanf (line, " %15s", salt) == 1 && line[0] == ' ')
                hex[0] = '\0';  /* an empty key: the line starts with its space */
            else
                return 2;
        }
        n = (int) strlen (hex) / 2;
        for (i = 0; i < n; i++)
        {
            char b[3] = { hex[2 * i], hex[2 * i + 1], 0 };
            key[i] = (char) strtol (b, NULL, 16);
        }
        key[n] = '\0';
        out = crypt (key, salt);
        printf ("%s\n", out ? out : "(null)");
    }
    return 0;
}
