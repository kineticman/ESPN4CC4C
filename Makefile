
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

.PHONY: help systemd-install systemd-uninstall systemd-reload systemd-status \
        resolver-start resolver-restart resolver-stop plan-run plan-timer-enable \
        plan-timer-disable plan-timer-next diag

help:
\t@echo "Targets:"
\t@echo "  systemd-install      Install @-templated units to /etc/systemd (needs sudo) and enable resolver+timer"
\t@echo "  systemd-uninstall    Disable and remove the installed units"
\t@echo "  systemd-reload       Reload systemd manager config"
\t@echo "  systemd-status       Show resolver + plan service + timer status"
\t@echo "  resolver-start       Start resolver service"
\t@echo "  resolver-restart     Restart resolver service"
\t@echo "  resolver-stop        Stop resolver service"
\t@echo "  plan-run             Run plan one-shot service now"
\t@echo "  plan-timer-enable    Enable + start plan timer"
\t@echo "  plan-timer-disable   Disable plan timer"
\t@echo "  plan-timer-next      Show next plan timer fire time"
\t@echo "  diag                 Run vc_diag.py (QUIET=1 to condense errors)"

systemd-install:
\tsudo install -Dm0644 $(PROJECT_DIR)/contrib/systemd/$(SERVICE_NS)-resolver-v2.service /etc/systemd/system/$(SERVICE_NS)-resolver-v2@.service
\tsudo install -Dm0644 $(PROJECT_DIR)/contrib/systemd/$(SERVICE_NS)-plan.service        /etc/systemd/system/$(SERVICE_NS)-plan@.service
\tsudo install -Dm0644 $(PROJECT_DIR)/contrib/systemd/$(SERVICE_NS)-plan.timer          /etc/systemd/system/$(SERVICE_NS)-plan@.timer
\tsudo sed -i "s|\\$${PROJECT_DIR}|$(PROJECT_DIR)|g" /etc/systemd/system/$(SERVICE_NS)-resolver-v2@.service
\tsudo sed -i "s|\\$${PROJECT_DIR}|$(PROJECT_DIR)|g" /etc/systemd/system/$(SERVICE_NS)-plan@.service
\t$(SYSTEMCTL) daemon-reload
\t$(SYSTEMCTL) enable --now $(RESOLVER)
\t$(SYSTEMCTL) enable --now $(PLAN_TMR)
\t@echo "Installed. Use 'make systemd-status' to verify."

systemd-uninstall:
\t-$(SYSTEMCTL) disable --now $(RESOLVER) $(PLAN_TMR) >/dev/null 2>&1 || true
\tsudo rm -f /etc/systemd/system/$(SERVICE_NS)-resolver-v2@.service
\tsudo rm -f /etc/systemd/system/$(SERVICE_NS)-plan@.service
\tsudo rm -f /etc/systemd/system/$(SERVICE_NS)-plan@.timer
\t$(SYSTEMCTL) daemon-reload
\t@echo "Removed unit files."

systemd-reload:
\t$(SYSTEMCTL) daemon-reload

systemd-status:
\t$(SYSTEMCTL) status $(RESOLVER) --no-pager || true
\t$(SYSTEMCTL) status $(PLAN_SVC) --no-pager || true
\t$(SYSTEMCTL) status $(PLAN_TMR) --no-pager || true
\t$(SYSTEMCTL) list-timers --all | grep -E '$(SERVICE_NS)-plan@|NEXT' || true

resolver-start:
\t$(SYSTEMCTL) start $(RESOLVER)

resolver-restart:
\t$(SYSTEMCTL) restart $(RESOLVER)

resolver-stop:
\t$(SYSTEMCTL) stop $(RESOLVER)

plan-run:
\t$(SYSTEMCTL) start $(PLAN_SVC)

plan-timer-enable:
\t$(SYSTEMCTL) enable --now $(PLAN_TMR)

plan-timer-disable:
\t$(SYSTEMCTL) disable --now $(PLAN_TMR) || true

plan-timer-next:
\t$(SYSTEMCTL) list-timers --all | grep -E '$(SERVICE_NS)-plan@|NEXT' || true

diag:
\t@. $(PROJECT_DIR)/.venv/bin/activate 2>/dev/null || true; \\
\tVC_RESOLVER_ORIGIN=$(RESOLVER_ORIGIN) \\
\tpython3 $(PROJECT_DIR)/tools/vc_diag.py --lane $(LANE) $(if $(QUIET),--quiet-errors,)
# Docker targets start
.PHONY: up down build verify logs cycle
up:    ; docker compose up -d
down:  ; docker compose down
build: ; docker compose build
verify:; ./espn4cc_verify.sh 192.168.86.72 8094
logs:  ; docker compose logs -f --tail=100
cycle: ; docker compose exec espn4cc /app/update_schedule.sh
# Docker targets end
