CC ?= cc
CFLAGS = -std=c99 -O1 -g -Wall -Wextra -Werror -pedantic -fsanitize=address,undefined
CORE = ../overlay/keyboards/a_jazz/ak820pro/app_menu
ASSETS = $(CORE)/app_font.c $(CORE)/app_icons.c
.PHONY: test
test: test_app_menu test_bridge test_raster test_idle
	./test_app_menu
	./test_bridge
	./test_raster
	./test_idle
test_app_menu: test_app_menu.c $(CORE)/app_menu.c $(CORE)/app_menu.h $(ASSETS)
	$(CC) $(CFLAGS) -I$(CORE) $(CORE)/app_menu.c $(ASSETS) $< -o $@
test_bridge: test_bridge.c $(CORE)/app_bridge.c $(CORE)/app_menu.c $(CORE)/app_bridge.h $(ASSETS)
	$(CC) $(CFLAGS) -I$(CORE) $(CORE)/app_menu.c $(ASSETS) $(CORE)/app_bridge.c $< -o $@
test_raster: test_raster.c $(CORE)/app_raster.c $(CORE)/app_menu.c $(ASSETS)
	$(CC) $(CFLAGS) -I$(CORE) $(CORE)/app_menu.c $(CORE)/app_raster.c $(ASSETS) $< -o $@
test_idle: test_idle.c $(CORE)/app_bridge.c $(CORE)/app_menu.c $(CORE)/app_raster.c $(ASSETS)
	$(CC) $(CFLAGS) -I$(CORE) $(CORE)/app_menu.c $(CORE)/app_raster.c $(CORE)/app_bridge.c $(ASSETS) $< -o $@

.PHONY: clean
clean:
	rm -f test_app_menu test_bridge test_raster test_idle
	rm -rf *.dSYM
