#include <assert.h>
#include "monitor-match.h"

int main(void) {
    /* Observed DP-5: Niri floors 2560/1.5; GDK rounds it to 1707. */
    assert(monitor_geometry_matches(4288, 0, 1707, 960, 4288, 0, 1706, 960));
    assert(monitor_geometry_matches(0, 0, 1536, 960, 0, 0, 1536, 960));
    assert(!monitor_geometry_matches(4287, 0, 1707, 960, 4288, 0, 1706, 960));
    assert(!monitor_geometry_matches(4288, 1, 1707, 960, 4288, 0, 1706, 960));
    assert(!monitor_geometry_matches(4288, 0, 1708, 960, 4288, 0, 1706, 960));
    assert(!monitor_geometry_matches(0, 0, 2752, 1152, 4288, 0, 1706, 960));
    return 0;
}
