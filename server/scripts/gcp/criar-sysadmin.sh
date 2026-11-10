#!/bin/bash
# Cria o sysadmin na GCP (página 19). O Léo roda UMA vez no Cloud Shell, com o projeto já escolhido
# (gcloud config set project <projeto>) e o faturamento ligado:
#   curl -fsSL https://raw.githubusercontent.com/lioevano/wiki-home-server/main/server/scripts/gcp/criar-sysadmin.sh | bash
# Cria as APIs, a conta de serviço sysadmin-vm (papéis mínimos), o bucket, a regra que recusa toda entrada, o alerta
# de orçamento de US$ 2, o segredo sysadmin-segredos, o vault cifrado e a VM e2-micro, que se configura sozinha no
# primeiro boot (ansible-pull). Pode ser repetido: APIs, conta, bucket, regras, orçamento e VM que já existem são
# mantidos, e se o segredo sysadmin-segredos já existe ele é REAPROVEITADO (nada de novo senha, chave SSH ou vault: o
# home já usa esses valores); isso também recria uma VM perdida. Só REGERAR=1 (com confirmação) gera tudo de novo.
# Variáveis opcionais: REGIAO, ZONA, TIPO, PROJETO, REPO_URL, REGERAR. Os valores digitados não aparecem na tela
# nem em linha de comando; os temporários somem ao sair.
set -euo pipefail

# Os campos do JSON são variáveis lidas por nome (${!campo}) e exportadas em json_segredos: o shellcheck não vê o uso.
# shellcheck disable=SC2034
main() {
    local REGIAO="${REGIAO:-us-east1}"
    local ZONA="${ZONA:-${REGIAO}-b}"
    local TIPO="${TIPO:-e2-micro}"
    local REPO_URL="${REPO_URL:-https://github.com/lioevano/wiki-home-server.git}"
    local VM="sysadmin" SEGREDO="sysadmin-segredos"
    local PROJETO="${PROJETO:-}" CONTA BUCKET TMP REUSAR=0 versao
    SEGREDO_FEITO=0

    # Ordem e nomes do JSON: os mesmos de scripts/gcp/separar_segredos.py (CAMPOS). Um teste confere.
    local CAMPOS=(anthropic_api_key gemini_api_key telegram_bot_sysadmin telegram_bot_aprovacoes telegram_chat_id
        tailscale_chave_sysadmin tailscale_chave_homeserver github_token_sysadmin github_token_carteiro
        vault_senha ssh_chave_privada ssh_chave_publica honcho_db_senha executor_token webhook_segredo
        dashboard_usuario dashboard_senha dashboard_segredo)

    erro() { echo "criar-sysadmin: $*" >&2; exit 1; }
    etapa() { echo; echo "== $* =="; }
    # A conta de serviço e as APIs demoram a propagar: repete algumas vezes antes de desistir.
    tentar() {
        local n
        for n in 1 2 3 4 5 6; do
            "$@" && return 0
            echo "  (tentativa $n/6 falhou; aguardando 10 s)" >&2
            sleep 10
        done
        return 1
    }

    umask 077
    TMP=$(mktemp -d)
    # Ao sair: apaga os temporários e, se algo falhou depois de o segredo existir, diz onde os valores estão.
    sair() {
        local rc=$?
        rm -rf "$1"
        if [ "$rc" -ne 0 ] && [ "$SEGREDO_FEITO" = 1 ]; then
            echo "O segredo $SEGREDO já foi gravado no Secret Manager: os valores estão lá. Rode o script de novo (ele o reaproveita)." >&2
        fi
    }
    # shellcheck disable=SC2064
    trap "sair '$TMP'" EXIT
    export PATH="$HOME/.local/bin:$PATH"
    export CLOUDSDK_CORE_DISABLE_PROMPTS=1

    # ---------------------------------------------------------------- 1/11
    etapa "1/11 Conferindo o gcloud e o projeto"
    command -v gcloud >/dev/null 2>&1 || erro "gcloud não encontrado (use o Cloud Shell)"
    command -v git >/dev/null 2>&1 || erro "git não encontrado"
    command -v openssl >/dev/null 2>&1 || erro "openssl não encontrado"
    command -v ssh-keygen >/dev/null 2>&1 || erro "ssh-keygen não encontrado"
    PROJETO="${PROJETO:-$(gcloud config get-value project 2>/dev/null || true)}"
    [ -n "$PROJETO" ] && [ "$PROJETO" != "(unset)" ] || erro "nenhum projeto: rode  gcloud config set project <projeto>"
    case "$REGIAO" in
        us-west1|us-central1|us-east1) ;;
        *) erro "região '$REGIAO' fora do nível gratuito (só us-west1, us-central1 ou us-east1); use REGIAO=..." ;;
    esac
    case "$ZONA" in
        "$REGIAO"-[a-f]) ;;
        *) erro "a zona '$ZONA' não pertence à região '$REGIAO'" ;;
    esac
    [ "$TIPO" = "e2-micro" ] || echo "AVISO: o tipo '$TIPO' não é o e2-micro gratuito: a VM será cobrada." >&2
    { : </dev/tty; } 2>/dev/null || erro "preciso de um terminal para pedir os segredos"
    CONTA="sysadmin-vm@${PROJETO}.iam.gserviceaccount.com"
    BUCKET="${PROJETO}-sysadmin"
    echo "projeto: $PROJETO | região: $REGIAO | zona: $ZONA | tipo: $TIPO"

    # Segredo já existe: reaproveita (padrão). Gerar tudo de novo troca a senha do vault, o vault de casa e a chave
    # SSH do host: só com REGERAR=1 e confirmação.
    if gcloud secrets describe "$SEGREDO" >/dev/null 2>&1; then
        SEGREDO_FEITO=1
        if [ "${REGERAR:-0}" = 1 ]; then
            local resp
            echo "ATENÇÃO: REGERAR=1 troca a senha do vault, o vault de casa, a chave SSH e todos os tokens."
            git clone --quiet --depth 1 --branch main "$REPO_URL" "$TMP/repo"
            if [ -e "$TMP/repo/server/ansible/inventories/home/group_vars/all/vault.yml" ]; then
                # O vault da main foi cifrado com a senha atual e continua valendo sobre o de entrada (que não tem
                # .base): com a senha nova, o executor não o lê e nenhum playbook roda.
                echo "ATENÇÃO: a main já tem vault.yml, cifrado com a senha atual. Com a senha nova, o executor deixa de" >&2
                echo "  ler o vault da main e nenhum playbook roda. Para recomeçar do zero: remova antes o vault.yml da" >&2
                echo "  main por PR e apague a VM (gcloud compute instances delete $VM --zone=$ZONA). Para só recriar" >&2
                echo "  uma VM perdida, rode sem REGERAR." >&2
            fi
            read -r -p "Gerar o segredo $SEGREDO de novo? [s/N] " resp </dev/tty
            [ "$resp" = "s" ] || erro "nada alterado"
        else
            REUSAR=1
            echo "O segredo $SEGREDO já existe: será reaproveitado (REGERAR=1 gera tudo de novo)."
        fi
    fi

    # ---------------------------------------------------------------- 2/11
    etapa "2/11 Ligando as APIs"
    gcloud services enable compute.googleapis.com secretmanager.googleapis.com iam.googleapis.com \
        storage.googleapis.com billingbudgets.googleapis.com --project="$PROJETO"

    # ---------------------------------------------------------------- 3/11
    etapa "3/11 Conta de serviço $CONTA"
    # Papéis mínimos: secretAccessor só no segredo (etapa 8, quando o segredo existe) e objectAdmin só no bucket
    # (etapa 4). Nenhum papel no projeto.
    if ! gcloud iam service-accounts describe "$CONTA" >/dev/null 2>&1; then
        gcloud iam service-accounts create sysadmin-vm --display-name="Sysadmin (VM)"
    fi

    # ---------------------------------------------------------------- 4/11
    etapa "4/11 Bucket gs://$BUCKET"
    if ! gcloud storage buckets describe "gs://${BUCKET}" >/dev/null 2>&1; then
        gcloud storage buckets create "gs://${BUCKET}" --location="$REGIAO" --default-storage-class=STANDARD \
            --uniform-bucket-level-access --public-access-prevention
    fi
    # Os backups (backup/) somem depois de 30 dias; entrada/ (o vault) não.
    cat >"$TMP/ciclo.json" <<'CICLO'
{"rule": [{"action": {"type": "Delete"}, "condition": {"age": 30, "matchesPrefix": ["backup/"]}}]}
CICLO
    gcloud storage buckets update "gs://${BUCKET}" --lifecycle-file="$TMP/ciclo.json"
    tentar gcloud storage buckets add-iam-policy-binding "gs://${BUCKET}" \
        --member="serviceAccount:${CONTA}" --role=roles/storage.objectAdmin >/dev/null

    # ---------------------------------------------------------------- 5/11
    etapa "5/11 Regra que recusa toda entrada"
    # Sem target-tags: vale para o projeto inteiro. O acesso é só pelo Tailscale (a VM sai para a internet, não recebe).
    if ! gcloud compute firewall-rules describe sysadmin-recusa-entrada >/dev/null 2>&1; then
        gcloud compute firewall-rules create sysadmin-recusa-entrada --network=default --direction=INGRESS \
            --priority=100 --action=DENY --rules=all --source-ranges=0.0.0.0/0 \
            --description="Sysadmin: recusa toda entrada (acesso só pelo Tailscale)"
    fi

    # Emergência: o IAP (35.235.240.0/20) alcançaria o SSH se o Tailscale falhar. Nasce DESLIGADA (--disabled) e,
    # com prioridade 90, vence a recusa quando ligada. Ligar/desligar: veja o fim do script.
    if ! gcloud compute firewall-rules describe sysadmin-iap-emergencia >/dev/null 2>&1; then
        gcloud compute firewall-rules create sysadmin-iap-emergencia --network=default --direction=INGRESS \
            --priority=90 --action=ALLOW --rules=tcp:22 --source-ranges=35.235.240.0/20 --disabled \
            --description="Sysadmin: SSH de emergência pelo IAP (desligada; ligue só quando precisar)"
    fi

    # ---------------------------------------------------------------- 6/11
    etapa "6/11 Alerta de orçamento de US\$ 2"
    local faturamento numero
    faturamento=$(gcloud billing projects describe "$PROJETO" --format='value(billingAccountName)' 2>/dev/null || true)
    faturamento="${faturamento#billingAccounts/}"
    numero=$(gcloud projects describe "$PROJETO" --format='value(projectNumber)')
    if [ -z "$faturamento" ]; then
        echo "AVISO: projeto sem conta de faturamento: crie o alerta de US\$ 2 à mão (Faturamento > Orçamentos)." >&2
    elif [ -n "$(gcloud billing budgets list --billing-account="$faturamento" --billing-project="$PROJETO" \
            --filter="displayName=sysadmin-2usd" --format='value(name)' 2>/dev/null)" ]; then
        echo "orçamento sysadmin-2usd já existe"
    elif ! gcloud billing budgets create --billing-account="$faturamento" --billing-project="$PROJETO" \
            --display-name=sysadmin-2usd \
            --budget-amount=2USD --filter-projects="projects/${numero}" \
            --threshold-rule=percent=0.5 --threshold-rule=percent=1.0; then
        echo "AVISO: não consegui criar o orçamento: crie o alerta de US\$ 2 à mão (Faturamento > Orçamentos)." >&2
    fi

    # Etapas 7 e 8 só quando o segredo ainda não existe (ou com REGERAR=1).
    coletar_e_gravar() {
        # ---------------------------------------------------------------- 7/11
        etapa "7/11 Segredos (o que você digita não aparece na tela)"
        local campo valor
        pedir() {
            # $1 = campo, $2 = o que pedir. Repete até vir algo; nunca imprime o valor.
            local v=""
            while [ -z "${v//[[:space:]]/}" ]; do
                read -rs -p "$2: " v </dev/tty
                echo >&2
            done
            printf -v "$1" '%s' "$v"
        }
        pedir anthropic_api_key "Chave da API da Anthropic"
        pedir gemini_api_key "Chave da API do Gemini"
        pedir telegram_bot_sysadmin "Token do bot do sysadmin (BotFather)"
        pedir telegram_bot_aprovacoes "Token do bot de aprovações (BotFather)"
        pedir telegram_chat_id "ID do seu chat no Telegram"
        pedir tailscale_chave_sysadmin "Chave de autenticação do Tailscale da VM (tag:sysadmin)"
        pedir tailscale_chave_homeserver "Chave de autenticação do Tailscale do host de casa (tag:homeserver)"
        pedir github_token_sysadmin "Token do GitHub da conta de máquina do sysadmin"
        pedir github_token_carteiro "Token do GitHub do carteiro (equipe)"

        # Gerados aqui (hexadecimal: sem caracteres que quebrem .env, URL ou shell).
        executor_token=$(openssl rand -hex 32)
        webhook_segredo=$(openssl rand -hex 32)
        honcho_db_senha=$(openssl rand -hex 24)
        dashboard_segredo=$(openssl rand -hex 32)
        dashboard_senha=$(openssl rand -hex 12)
        vault_senha=$(openssl rand -hex 24)
        dashboard_usuario="leo"

        # Chave SSH do executor (entra no host de casa pelo preparar-host.sh), só neste diretório temporário.
        mkdir "$TMP/ssh"
        ssh-keygen -t ed25519 -N "" -C "sysadmin-executor" -f "$TMP/ssh/id" -q
        ssh_chave_privada=$(<"$TMP/ssh/id")
        ssh_chave_publica=$(<"$TMP/ssh/id.pub")

        # ---------------------------------------------------------------- 8/11
        etapa "8/11 Segredo $SEGREDO (Secret Manager)"
        for campo in "${CAMPOS[@]}"; do
            valor="${!campo:-}"
            [ -n "$valor" ] || erro "campo sem valor: $campo"
        done
        # O JSON nasce no python3, que lê as variáveis do AMBIENTE (nunca de argumento de linha de comando), e vai pelo
        # stdin ao gcloud.
        json_segredos() {
            ( export "${CAMPOS[@]}"
              python3 -c 'import json, os, sys; print(json.dumps({c: os.environ[c] for c in sys.argv[1:]}))' "${CAMPOS[@]}" )
        }
        if gcloud secrets describe "$SEGREDO" >/dev/null 2>&1; then
            json_segredos | gcloud secrets versions add "$SEGREDO" --data-file=- >/dev/null
            SEGREDO_FEITO=1
            echo "nova versão de $SEGREDO"
        else
            json_segredos | gcloud secrets create sysadmin-segredos --data-file=- --replication-policy=automatic >/dev/null
            SEGREDO_FEITO=1
            echo "segredo $SEGREDO criado"
        fi
        tentar gcloud secrets add-iam-policy-binding "$SEGREDO" \
            --member="serviceAccount:${CONTA}" --role=roles/secretmanager.secretAccessor >/dev/null
    }

    if [ "$REUSAR" = 1 ]; then
        etapa "7/11 e 8/11 Segredo $SEGREDO já existe: reaproveitado"
        # Garante o papel da conta de serviço também numa repetição (idempotente).
        tentar gcloud secrets add-iam-policy-binding "$SEGREDO" \
            --member="serviceAccount:${CONTA}" --role=roles/secretmanager.secretAccessor >/dev/null
    else
        coletar_e_gravar
    fi
    # ---------------------------------------------------------------- 9/11
    etapa "9/11 Repositório e vault cifrado (gerar_vault.py, aqui no Cloud Shell)"
    [ -d "$TMP/repo" ] || git clone --quiet --depth 1 --branch main "$REPO_URL" "$TMP/repo"
    # Uma fonte só para a versão: o group_vars do repositório (ops_ansible_core_version). O startup-script usa a mesma.
    versao=$(sed -n 's/^ops_ansible_core_version: *"\([0-9][0-9.]*\)".*/\1/p' \
        "$TMP/repo/server/ansible/inventories/home/group_vars/all/main.yml" | head -n 1)
    [[ "$versao" =~ ^[0-9]+\.[0-9]+\.[0-9]+$ ]] || erro "não achei ops_ansible_core_version no group_vars"
    echo "ansible-core $versao ($(python3 -V))"
    # Com o segredo reaproveitado: se a main já tem vault.yml, a main manda: nada de vault novo, e o entrada/ que
    # sobrou da fase 1 é apagado (a VM recriada o semearia no saida/; sem .base ele não valeria sobre a main, mas não
    # fica por lá para virar PR por engano). Senão, o vault de entrada só é (re)feito se faltar no bucket.
    local gerar_vault=1
    if [ "$REUSAR" = 1 ] && [ -e "$TMP/repo/server/ansible/inventories/home/group_vars/all/vault.yml" ]; then
        gerar_vault=0
        gcloud storage rm "gs://${BUCKET}/entrada/vault.yml" >/dev/null 2>&1 || true
        echo "a main já tem vault.yml: a main manda (não gero vault e apaguei o entrada/; o executor lê o da main)"
    elif [ "$REUSAR" = 1 ] && gcloud storage ls "gs://${BUCKET}/entrada/vault.yml" >/dev/null 2>&1; then
        gerar_vault=0
        echo "gs://${BUCKET}/entrada/vault.yml já existe: mantido"
    fi
    if [ "$gerar_vault" = 1 ]; then
        if [ "$REUSAR" = 1 ]; then
            echo "AVISO: vault de entrada ausente: gero um com a vault_senha do segredo (confira se o do repositório é outro)." >&2
            # A senha vem do segredo para um arquivo 0600 (redirecionamento: nunca em linha de comando).
            gcloud secrets versions access latest --secret="$SEGREDO" \
                | python3 -c 'import json, sys; print(json.load(sys.stdin)["vault_senha"])' >"$TMP/senha-vault"
        else
            # É a mesma vault_senha do segredo.
            printf '%s\n' "$vault_senha" >"$TMP/senha-vault"
        fi
        chmod 600 "$TMP/senha-vault"
        if ! python3 -m pip install --user --quiet "ansible-core==${versao}" 2>/dev/null; then
            python3 -m pip install --user --quiet --break-system-packages "ansible-core==${versao}" \
                || erro "não consegui instalar ansible-core==${versao} (exige Python 3.12 ou mais novo; aqui: $(python3 -V))"
        fi
        # Mostra o bloco "anote" na tela do Léo.
        ( cd "$TMP/repo" && python3 server/scripts/gerar_vault.py --senha-vault-arquivo "$TMP/senha-vault" --saida "$TMP/vault.yml" )
        # shellcheck disable=SC2016
        head -n 1 "$TMP/vault.yml" | grep -q '^\$ANSIBLE_VAULT;' || erro "o vault.yml gerado não está cifrado"
        gcloud storage cp "$TMP/vault.yml" "gs://${BUCKET}/entrada/vault.yml"
    fi

    # ---------------------------------------------------------------- 10/11
    etapa "10/11 VM $VM"
    # Startup-script (metadado da VM, sem segredos): ansible-core fixado num venv, coleções do requirements.yml e o
    # mesmo ansible-pull da unit sysadmin-pull.service do role (comando e ambiente iguais; um teste confere). Roda
    # só no primeiro boot que der certo; depois o timer diário cuida das atualizações.
    cat >"$TMP/startup.sh.modelo" <<'STARTUP'
#!/bin/bash
# Primeiro boot do sysadmin (página 19): instala o ansible-core e faz o primeiro ansible-pull da main.
# O progresso aparece no console serial (gcloud compute instances get-serial-port-output).
set -uo pipefail
MARCA=/var/lib/sysadmin-primeiro-boot
[ ! -e "$MARCA" ] || exit 0
export HOME=/root DEBIAN_FRONTEND=noninteractive
log() { echo "sysadmin-boot: $*"; }

# Cada comando termina em "|| return 1": dentro de um "if" o set -e não vale.
primeiro_boot() {
    # No Ubuntu recém-criado o apt-daily/unattended-upgrades costuma segurar o lock do dpkg: espera até 10 min.
    log "apt: pacotes" || return 1
    apt-get -o DPkg::Lock::Timeout=600 update -q || return 1
    apt-get -o DPkg::Lock::Timeout=600 install -y -q git curl ca-certificates python3-venv || return 1
    # O ansible do apt (2.16) não serve para a community.general atual: ansible-core fixado num venv (a versão é a
    # ops_ansible_core_version do group_vars, trocada pelo criar-sysadmin.sh na criação).
    log "ansible-core @VERSAO_ANSIBLE@" || return 1
    python3 -m venv /opt/ansible || return 1
    /opt/ansible/bin/pip install --quiet "ansible-core==@VERSAO_ANSIBLE@" || return 1
    for b in ansible ansible-galaxy ansible-pull ansible-playbook ansible-config; do
        ln -sf "/opt/ansible/bin/$b" "/usr/local/bin/$b" || return 1
    done
    log "coleções do Ansible" || return 1
    curl -fsSL https://raw.githubusercontent.com/lioevano/wiki-home-server/main/server/ansible/requirements.yml -o /tmp/requirements.yml || return 1
    ansible-galaxy collection install -r /tmp/requirements.yml -p /usr/share/ansible/collections || return 1
    rm -f /tmp/requirements.yml
    # Igual à unit sysadmin-pull.service: de "/", com o ansible.cfg do clone e sem group_vars automáticos.
    export PATH=/snap/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin
    export ANSIBLE_CONFIG=/opt/sysadmin/pull/server/ansible/ansible.cfg
    export ANSIBLE_VARS_ENABLED=
    cd / || return 1
    log "ansible-pull" || return 1
    ansible-pull -U https://github.com/lioevano/wiki-home-server.git -C main -d /opt/sysadmin/pull -i server/ansible/inventories/home/hosts.ini -l sysadmin-gcp server/ansible/playbooks/setup-sysadmin.yml || return 1
}

for tentativa in 1 2 3; do
    log "primeiro boot, tentativa $tentativa/3"
    if primeiro_boot; then
        touch "$MARCA"
        log "concluído"
        exit 0
    fi
    log "falhou"
    [ "$tentativa" -eq 3 ] || sleep 60
done
log "desistindo: veja o console serial e rode o startup-script de novo (sudo google_metadata_script_runner startup)"
exit 1
STARTUP
    sed "s|@VERSAO_ANSIBLE@|${versao}|g" "$TMP/startup.sh.modelo" >"$TMP/startup.sh"
    if gcloud compute instances describe "$VM" --zone="$ZONA" >/dev/null 2>&1; then
        echo "a VM $VM já existe: só atualizo o startup-script (reinício a cargo do Léo)"
        gcloud compute instances add-metadata "$VM" --zone="$ZONA" --metadata-from-file=startup-script="$TMP/startup.sh"
    else
        tentar gcloud compute instances create "$VM" --zone="$ZONA" --machine-type="$TIPO" \
            --image-family=ubuntu-2404-lts-amd64 --image-project=ubuntu-os-cloud \
            --boot-disk-size=30GB --boot-disk-type=pd-standard \
            --service-account="$CONTA" --scopes=cloud-platform \
            --shielded-secure-boot --shielded-vtpm --shielded-integrity-monitoring \
            --metadata-from-file=startup-script="$TMP/startup.sh"
    fi

    # ---------------------------------------------------------------- 11/11
    etapa "11/11 Senhas e acesso de emergência"
    if [ "$REUSAR" = 1 ]; then
        echo "Segredo reaproveitado: nada foi gerado agora. A senha do painel e a do vault estão no Secret Manager:"
        echo "  gcloud secrets versions access latest --secret=$SEGREDO | python3 -c 'import json, sys; d = json.load(sys.stdin); print(d[\"dashboard_usuario\"], d[\"dashboard_senha\"], d[\"vault_senha\"])'"
    else
        echo "Guarde estas senhas (aparecem só agora):"
        echo "  painel do Hermes: usuário  $dashboard_usuario"
        echo "  painel do Hermes: senha    $dashboard_senha"
        echo "  senha do vault (ansible-vault): $vault_senha"
    fi
    echo
    echo "SSH de emergência (se o Tailscale falhar): a regra sysadmin-iap-emergencia está DESLIGADA. Para usar:"
    echo "  gcloud compute firewall-rules update sysadmin-iap-emergencia --no-disabled"
    echo "  gcloud compute ssh $VM --zone=$ZONA --tunnel-through-iap"
    echo "e depois desligue:  gcloud compute firewall-rules update sysadmin-iap-emergencia --disabled"
    echo
    echo "A VM se configura sozinha (de 20 a 40 min: as imagens são construídas na e2-micro). Acompanhe com:"
    echo "  gcloud compute instances get-serial-port-output $VM --zone=$ZONA | tail -n 30"
    echo "Quando o nó 'sysadmin' aparecer no Tailscale, siga a página 19 (teste de ponta a ponta)."
    # Os temporários (chave SSH, senha do vault, clone) são apagados pelo trap ao sair.
}

main "$@"
