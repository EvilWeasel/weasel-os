/* Niri and GDK can round fractional logical extents in opposite directions.
 * Position remains exact; never accept a larger mismatch or select a default.
 */
static int monitor_extent_matches(int actual, int expected) {
    return actual > 0 && expected > 0 &&
        (actual == expected || actual == expected + 1 || actual + 1 == expected);
}

static int monitor_geometry_matches(int x, int y, int width, int height,
                                    int expected_x, int expected_y,
                                    int expected_width, int expected_height) {
    return x == expected_x && y == expected_y &&
        monitor_extent_matches(width, expected_width) &&
        monitor_extent_matches(height, expected_height);
}
