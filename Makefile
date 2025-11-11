# Makefile — ESPN4CC helper targets
# Usage examples:
#   make systemd-install USER=brad PROJECT_DIR=/home/brad/Projects/ESPN4CC
#   make systemd-status USER=brad
#   make plan-run USER=brad
#   make resolver-restart USER=brad
#   make diag LANE=eplus11 QUIET=1
#
# Vars (override on CLI):
USER        ?= $(shell id -un)
PROJECT_DIR ?= $(HOME)/Projects/ESPN4CC
SERVICE_NS  ?= vc
RESOLVER    ?= $(SERVICE_NS)-resolver-v2@$(USER).service
PLAN_SVC    ?= $(SERVICE_NS)-plan@$(USER).service
PLAN_TMR    ?= $(SERVICE_NS)-plan@$(USER).timer

# Tools
SYSTEMCTL   ?= systemctl
JOURNALCTL  ?= journalctl
CURL        ?= curl

# Diag opts
LANE        ?= eplus11
QUIET       ?= 1
RESOLVER_ORIGIN ?= http://127.0.0.1:8094

# --- Verify host/port (prefer VC_RESOLVER_BASE_URL from env) ---
# Parse VC_RESOLVER_BASE_URL like "http://192.168.x.y:8094"
HOST ?= $(shell printf "%s" "$${VC_RESOLVER_BASE_URL:-}" | sed -n 's#http://\([0-9.]*\):\([0-9]*\).*#\1#p')
PORT ?= $(shell printf "%s" "$${VC_RESOLVER_BASE_URL:-}" | sed -n 's#http://\([0-9.]*\):\([0-9]*\).*#\2#p')
ifeq ($(HOST),)
HOST := $(shell hostname -I | awk '{print $$1}')
endif
ifeq ($(PORT),)
PORT := 8094
endif

.PHONY: help systemd-install systemd-uninstall systemd-reload systemd-status \
        resolver-start resolver-restart resolver-stop plan-run plan-timer-enable \
        plan-timer-disable plan-timer-next diag up down build verify logs cycle

help:
	@echo "Targets:"
	@echo "  systemd-install      Install @-templated units to /etc/systemd (needs sudo) and enable resolver+timer"
	@echo "  systemd-uninstall    Disable and remove the installed units"
	@echo "  systemd-reload       Reload systemd manager config"
	@echo "  systemd-status       Show resolver + plan service + timer status"
	@echo "  resolver-start       Start resolver service"
	@echo "  resolver-restart     Restart resolver service"
	@echo "  resolver-stop        Stop resolver service"
	@echo "  plan-run             Run plan one-shot service now"
	@echo "  plan-timer-enable    Enable + start plan timer"
	@echo "  plan-timer-disable   Disable plan timer"
	@echo "  plan-timer-next      Show next plan timer fire time"
	@echo "  diag                 Run vc_diag.py (QUIET=1 to condense errors)"
	@echo "  up/down/build/logs   Docker compose helpers"
	@echo "  verify               Run espn4cc_verify.sh against $(HOST):$(PORT)"
	@echo "  cycle                Run in-container refresh script"

systemd-install:
	sudo install -Dm0644 $(PROJECT_DIR)/contrib/systemd/$(SERVICE_NS)-resolver-v2.service /etc/systemd/system/$(SERVICE_NS)-resolver-v2@.service
	sudo install -Dm0644 $(PROJECT_DIR)/contrib/systemd/$(SERVICE_NS)-plan.service        /etc/systemd/system/$(SERVICE_NS)-plan@.service
	sudo install -Dm0644 $(PROJECT_DIR)/contrib/systemd/$(SERVICE_NS)-plan.timer          /etc/systemd/system/$(SERVICE_NS)-plan@.timer
	sudo sed -i "s|\$${PROJECT_DIR}|$(PROJECT_DIR)|g" /etc/systemd/system/$(SERVICE_NS)-resolver-v2@.service
	sudo sed -i "s|\$${PROJECT_DIR}|$(PROJECT_DIR)|g" /etc/systemd/system/$(SERVICE_NS)-plan@.service
	$(SYSTEMCTL) daemon-reload
	$(SYSTEMCTL) enable --now $(RESOLVER)
	$(SYSTEMCTL) enable --now $(PLAN_TMR)
	@echo "Installed. Use 'make systemd-status' to verify."

systemd-uninstall:
	-$(SYSTEMCTL) disable --now $(RESOLVER) $(PLAN_TMR) >/dev/null 2>&1 || true
	sudo rm -f /etc/systemd/system/$(SERVICE_NS)-resolver-v2@.service
	sudo rm -f /etc/systemd/system/$(SERVICE_NS)-plan@.service
	sudo rm -f /etc/systemd/system/$(SERVICE_NS)-plan@.timer
	$(SYSTEMCTL) daemon-reload
	@echo "Removed unit files."

systemd-reload:
	$(SYSTEMCTL) daemon-reload

systemd-status:
	$(SYSTEMCTL) status $(RESOLVER) --no-pager || true
	$(SYSTEMCTL) status $(PLAN_SVC) --no-pager || true
	$(SYSTEMCTL) status $(PLAN_TMR) --no-pager || true
	$(SYSTEMCTL) list-timers --all | grep -E '$(SERVICE_NS)-plan@|NEXT' || true

resolver-start:
	$(SYSTEMCTL) start $(RESOLVER)

resolver-restart:
	$(SYSTEMCTL) restart $(RESOLVER)

resolver-stop:
	$(SYSTEMCTL) stop $(RESOLVER)

plan-run:
	$(SYSTEMCTL) start $(PLAN_SVC)

plan-timer-enable:
	$(SYSTEMCTL) enable --now $(PLAN_TMR)

plan-timer-disable:
	$(SYSTEMCTL) disable --now $(PLAN_TMR) || true

plan-timer-next:
	$(SYSTEMCTL) list-timers --all | grep -E '$(SERVICE_NS)-plan@|NEXT' || true

diag:
	@. $(PROJECT_DIR)/.venv/bin/activate 2>/dev/null || true; \
	VC_RESOLVER_ORIGIN=$(RESOLVER_ORIGIN) \
	python3 $(PROJECT_DIR)/tools/vc_diag.py --lane $(LANE) $(if $(QUIET),--quiet-errors,)

# Docker targets
up:    ; docker compose up -d
down:  ; docker compose down
build: ; docker compose build
logs:  ; docker compose logs -f --tail=120
verify:; contrib/diagnostics/espn4cc_verify.sh $(HOST) $(PORT)
cycle: ; docker compose exec espn4cc /app/bin/refresh_in_container.sh
