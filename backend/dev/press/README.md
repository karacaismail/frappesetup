# Press geliştirme ortamı

Bu kurulum ayrı bir yerel Press sitesi açar. Press, kiracı sitelerini yönetir.

Frappe v16.50.0 ve Press v0.154.1 kullanılır. Python sürümü 3.14.8'dir.
Uyum yamaları yalnız yerel Press denemesi içindir.
Sunucu kurma ve Ansible bu kurulumda çalışmaz.

Komutları depo kökünde çalıştırın. Önce mevcut deneme imajını Colima'ya kopyalayın.

```sh
docker --context colima save press-local-bench:latest | docker --context colima-factory load
docker --context colima-factory tag press-local-bench:latest fs-press-tr-base:py3.14.8
```

Sahte parolalarla yalnız yerel ortamı açın.

```sh
export PRESS_WEB_PORT="$((${PANE_PORT:?} + 3))"
export PRESS_SOCKET_PORT="$((PANE_PORT + 4))"
press_compose() {
  docker --context colima-factory compose --env-file backend/dev/press/.env.example -f backend/dev/compose.press.yaml "$@"
}
press_compose up -d
press_compose exec -T --user root web install -d -o frappe -g frappe /home/frappe/benches /home/frappe/benches/source /opt/press-local/scripts
press_compose cp backend/dev/press/patch-py314.sh web:/opt/press-local/scripts/patch-py314.sh
press_compose cp backend/apps/press_tr web:/home/frappe/benches/source/
press_compose exec -T web bash -s < backend/dev/press/install.sh
press_compose cp backend/libs/oidc_verify web:/home/frappe/benches/source/
press_compose exec -T --workdir /home/frappe/benches/frappe-bench web \
  env/bin/python -m pip install ../source/oidc_verify
press_compose exec -d web bash -lc 'cd /home/frappe/benches/frappe-bench && exec bench start > logs/bench-start.log 2>&1'
```

Site ayarları [Press TR kurulumunda](../../apps/press_tr/README.md) yer alır.

Duman testi, sitenin yanıtını ve kurulu uygulamaları denetler.

```sh
sh backend/apps/press_tr/tests/smoke.sh
```

İş bitince yalnız bu işe ait ortamı kapatın.

```sh
press_compose down
```
