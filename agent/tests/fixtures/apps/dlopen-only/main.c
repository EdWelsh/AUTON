/* Loads a plugin whose name is assembled at run time from plugins.conf.
 * No library name appears in any source file: static reading cannot know
 * what this program needs. Observation can. (application-to-environment A5) */
#include <dlfcn.h>
#include <stdio.h>
#include <string.h>

int main(void)
{
	char stem[32] = {0};
	char name[64];
	FILE *f = fopen("/app/plugins.conf", "r");

	if (!f || !fgets(stem, sizeof stem, f)) {
		fprintf(stderr, "no plugins.conf\n");
		return 2;
	}
	fclose(f);
	stem[strcspn(stem, "\n")] = 0;
	snprintf(name, sizeof name, "lib%s.so.%d", stem, 1);
	if (!dlopen(name, RTLD_NOW)) {
		fprintf(stderr, "cannot load %s: %s\n", name, dlerror());
		return 1;
	}
	printf("loaded %s\n", name);
	return 0;
}
