# ha-runscaler

Integração do Home Assistant para o [runscaler](https://github.com/PatrikGuerra/runscaler) (fork de `ysya/runscaler`), que sobe runners efêmeros do GitHub Actions em containers Docker.

Com ela, o Home Assistant mostra o estado do runner, os jobs, o disco e o log. Também deixa mudar uma lista fechada de configurações e reiniciar ou parar o runscaler.

## Como funciona

```text
Home Assistant (network_mode: host)
  ├── GET  http://127.0.0.1:8089/healthz           → sensores
  ├── lê   /runscaler-exchange/outbox/*.json       → config atual, resultado do pedido
  ├── lê   /runscaler-exchange/logs/runner.log     → log
  └── grava /runscaler-exchange/inbox/request.json → pedido
runscaler: internal/inbox valida o pedido → aplica → drain → reinicia
```

A integração nunca fala com o Docker. Ela só grava um pedido em JSON. Quem decide é o runscaler: ele recusa qualquer campo fora da lista e copia da config atual os campos fixos (`dind`, socket, rede, GitHub App).

O contrato JSON é definido no fork, em `internal/inbox/testdata/contract/`. Uma cópia fica em `tests/fixtures/contract/`, e os testes conferem que a integração grava o mesmo formato.

## Requisitos

- Home Assistant **Container** 2026.11 ou mais novo.
- runscaler do fork, com `RUNNER_EXCHANGE_DIR` ligado e o `/healthz` publicado em `127.0.0.1:8089`. O passo a passo está em `deploy/homeassistant/README.md`, no fork.
- A pasta `/opt/runscaler/exchange` do host montada no container do HA em `/runscaler-exchange`.

## Instalar

1. Copie a pasta `custom_components/runscaler` para `/config/custom_components/runscaler` do HA. No Pi, `/config` é `/opt/homeassistant/config`:

   ```bash
   scp -r custom_components/runscaler orange@192.168.1.118:/tmp/runscaler
   ssh orange@192.168.1.118 'sudo mkdir -p /opt/homeassistant/config/custom_components && sudo rm -rf /opt/homeassistant/config/custom_components/runscaler && sudo mv /tmp/runscaler /opt/homeassistant/config/custom_components/'
   ```

2. Reinicie o Home Assistant.
3. Em **Configurações → Dispositivos e serviços → Adicionar integração**, procure **Runscaler**.
4. Confirme os dois campos:

   | Campo | Padrão |
   |---|---|
   | URL do health | `http://127.0.0.1:8089/healthz` |
   | Pasta de troca | `/runscaler-exchange` |

## Entidades

Os ids são fixos em inglês, seja qual for o idioma do HA.

| Tipo | Entidades |
|---|---|
| Estado | `binary_sensor.runscaler_reachable`, `binary_sensor.runscaler_connected`, `sensor.runscaler_status`, `sensor.runscaler_assigned_jobs`, `sensor.runscaler_running_jobs`, `sensor.runscaler_idle_runners`, `sensor.runscaler_jobs_started`, `sensor.runscaler_jobs_completed`, `sensor.runscaler_disk_free`, `sensor.runscaler_last_error`, `sensor.runscaler_version` |
| Log | `sensor.runscaler_last_log_line`. O atributo `lines` tem as últimas 50 linhas e não vai para o banco do HA |
| Config (rascunho) | `text.runscaler_url`, `text.runscaler_name`, `text.runscaler_runner_image`, `number.runscaler_max_runners`, `number.runscaler_concurrent`, `number.runscaler_min_runners`, `number.runscaler_docker_memory`, `number.runscaler_docker_cpu`, `number.runscaler_docker_pids_limit`, `number.runscaler_drain_timeout`, `select.runscaler_log_level` |
| Pedido | `binary_sensor.runscaler_pending_changes`, `sensor.runscaler_last_request` (`pending` / `applied` / `rejected` / `timeout`) |
| Botões | `button.runscaler_apply_config`, `button.runscaler_discard_changes`, `button.runscaler_restart`, `button.runscaler_stop_now` |

### Mudar a config

Mudar um campo **não** mexe no runscaler. Só muda um rascunho, e `binary_sensor.runscaler_pending_changes` liga. O botão **Aplicar config** manda todos os campos de uma vez. O runscaler valida, espera os jobs terminarem e reinicia.

- O rascunho fica só na memória. Se o HA reiniciar, ele volta para a config atual.
- Só pode haver um pedido por vez. Um segundo pedido dá erro até o primeiro ter resposta.
- Se o runscaler recusar o pedido ou não responder em 120 s, aparece uma notificação no HA. Também é disparado o evento `runscaler_request_finished`.

## Exemplos

- `examples/dashboard.yaml`: dashboard com as abas Status, Config, Ações e Logs. Os botões pedem confirmação.
- `examples/automations.yaml`: avisos de runner desconectado, disco baixo e pedido recusado.

## Segurança

- O HA não tem permissão por entidade. **Qualquer usuário do HA** pode aplicar uma config ou parar o runner.
- O `/healthz` fica só em `127.0.0.1`. Ele não aparece na rede de casa, e os jobs não o alcançam.
- A troca do `.pem` da GitHub App não passa pela integração. Ela continua por `scp`.

## Desenvolvimento

```bash
python3.14 -m venv .venv && . .venv/bin/activate
pip install -r requirements_test.txt
pytest -q
```

`tests/test_exchange.py` não precisa do Home Assistant, então roda em qualquer Python 3.12+. Os outros testes usam `pytest-homeassistant-custom-component`, que pede Python 3.14 e não roda no Windows. O CI roda tudo.
