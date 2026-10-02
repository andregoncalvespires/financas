# Finanças

[Português (Brasil)](README.md) · **Português (Portugal)** · [English](README.en.md)

Aplicação de finanças pessoais e da família, **auto-alojada**: instala-a no seu próprio computador ou servidor, os dados ficam consigo, e várias pessoas podem usá-la com privacidade. Funciona no navegador e pode ser instalada no telemóvel como aplicação (PWA).

## Instalação em 3 passos

Só precisa do **Docker** com Compose (Docker Desktop no Windows e no macOS; Docker Engine no Linux).

**1. Descarregue o ficheiro modelo.** Crie uma pasta e guarde nela o [`docker-compose.yml`](https://raw.githubusercontent.com/andregoncalvespires/financas/main/docker-compose.yml). Num terminal:

```bash
mkdir financas && cd financas
curl -fsSLO https://raw.githubusercontent.com/andregoncalvespires/financas/main/docker-compose.yml
```

**2. Preencha duas linhas.** Abra o `docker-compose.yml` num editor de texto e preencha, no bloco "EDITE AQUI" no topo, `SMTP_USER` (o seu e-mail) e `SMTP_PASSWORD` (a palavra-passe do e-mail). É por esse e-mail que a aplicação envia os códigos de acesso.

<details>
<summary><b>Usa Gmail? Como obter a palavra-passe (1 minuto)</b></summary>

1. Na sua conta Google, ative a **verificação em dois passos** (Conta Google → Segurança).
2. Abra <https://myaccount.google.com/apppasswords> e crie uma **palavra-passe de aplicação**. A Google mostra 16 letras: copie-as sem os espaços.
3. No `docker-compose.yml`:
   ```yaml
   SMTP_USER: "o.seu.nome@gmail.com"
   SMTP_PASSWORD: "abcdefghijklmnop"
   ```
</details>

**3. Inicie e abra.**

```bash
docker compose up -d
```

Abra <http://localhost:8472>, escreva o seu e-mail, introduza o código que chegou à caixa de entrada e está pronto. Na primeira execução a aplicação gera sozinha as palavras-passe internas (base de dados e segurança); não precisa de criar nem de anotar nada.

Para usar noutro dispositivo da mesma rede (telemóvel, tablet), abra `http://IP-DO-COMPUTADOR:8472`.

Se algo não funcionar, veja [Problemas comuns](#problemas-comuns).

## Ecrãs

<p align="center">
<img src="docs/img/01-inicio.png" width="180" alt="Início"> <img src="docs/img/02-proximos-eventos.png" width="180" alt="Próximos eventos"> <img src="docs/img/05-lancamentos.png" width="180" alt="Lançamentos"> <img src="docs/img/06-filtros.png" width="180" alt="Filtros"> <img src="docs/img/07-filtro-cartao.png" width="180" alt="Consulta por cartão"> <img src="docs/img/08-cartoes.png" width="180" alt="Cartões e faturas">
</p>

<sub>Dados fictícios, apenas para demonstração.</sub>

## O que a aplicação faz

**Contas e saldos**
- Contas à ordem, poupança, investimentos, dinheiro vivo, contas de terceiros e **benefícios** (cartão de refeição ou de alimentação) com **carregamento mensal** automático, que pode ajustar ou desativar. Cria os seus próprios **tipos de conta**.
- **Saldo disponível calculado**: saldo atual menos o que está previsto sair (contas a pagar, faturas e transferências planeadas) no período escolhido, de 7 a 90 dias.

**Movimentos**
- Despesas, receitas e **transferências entre contas** (da conta à ordem para a poupança, para o dinheiro, etc.), que não distorcem as receitas e despesas do mês.
- **Data de competência** (o mês a que pertence) e **data de caixa** (quando o dinheiro se move).
- **Previsto ou efetivado**: planeie pagamentos e recebimentos futuros, confirme quando acontecerem ou volte a pôr um movimento como previsto se o confirmou por engano.
- **Movimentos recorrentes** (renda, ordenado, subscrições), compras a prestações, beneficiários com categoria sugerida e um plano de categorias enxuto que pode editar e fundir.

**Cartão de crédito**
- Faturas com fecho e vencimento, compras a prestações e pagamento da fatura a partir de uma conta.
- **Importar a fatura em PDF** (com ou sem palavra-passe): a aplicação lê as compras, compara com o que já lançou, mostra as diferenças de valor para decidir e só grava depois da sua conferência. Requer a leitura por IA ativada.
- **Cartões adicionais** e virtuais: as compras de todos caem na fatura do titular. Um familiar convidado como portador vê apenas as suas próprias despesas.

**Planeamento**
- **Orçamento** por categoria com regras de vigência: sem data final, por número de meses, em meses específicos do ano ou ajuste de um único mês.
- **Início**: resumo por grupos (disponível, benefícios, investimentos, outros e total) e **próximos eventos** (contas a pagar e a receber, faturas e transferências planeadas), com botão para confirmar o que já aconteceu.

**Leitura de comprovativos com IA (opcional)**
- Tire uma fotografia a um talão, fatura, comprovativo de transferência ou extrato e a aplicação sugere valor, data, estabelecimento e categoria. Revê sempre antes de guardar.

**Várias pessoas, com privacidade**
- Cada pessoa vê apenas os seus próprios dados. Partilha **conta a conta** (ou um cartão) com quem quiser, como leitor, editor ou gestor, e retira o acesso quando quiser.
- **Aviso de novos registos:** a cada conta nova, o e-mail do administrador (o `SMTP_USER` do `docker-compose.yml`) recebe um aviso.
- Entrada **sem palavra-passe**: chega um código de 6 dígitos por e-mail e o dispositivo fica memorizado. Pode ver e revogar os dispositivos ligados.
- O isolamento entre pessoas é garantido pela própria base de dados (segurança ao nível da linha do PostgreSQL), e não apenas pelo código da aplicação.

**Os seus dados são seus**
- **Exportar tudo** (folha de cálculo Excel com movimentos e faturas, mais os comprovativos) e **eliminar a própria conta e todos os dados** a qualquer momento, em Mais → Meu perfil. O ecrã **Sobre o aplicativo** mostra a versão e as novidades.

> A interface da aplicação está em português do Brasil.

## Configurações opcionais

<details>
<summary><b>Outro fornecedor de e-mail (que não seja o Gmail)</b></summary>

Qualquer servidor SMTP que aceite **utilizador e palavra-passe** serve (um serviço de envio como Brevo, Mailgun ou Amazon SES, ou o servidor de e-mail do seu domínio). No `docker-compose.yml`, retire o `#` e ajuste `SMTP_HOST`, `SMTP_PORT` (587 = STARTTLS, 465 = SSL) e, se quiser, `MAIL_FROM`, com os dados que o fornecedor indica no painel dele.
</details>

<details>
<summary><b>Área de administração (quem se registou e quando acedeu)</b></summary>

Opcional e só de leitura. Preencha `ADMIN_EMAIL: "o@seu.email"` no `docker-compose.yml` e execute `docker compose up -d`. Quem entrar com esse e-mail passa a ver **Mais › Administração**, com a lista de pessoas registadas, a data de registo, o último acesso e quantas contas e cartões ativos cada uma tem (só aqueles de que é dona). A área **não mostra lançamentos, valores nem nomes de contas**. Com `ADMIN_EMAIL` vazio (a predefinição), a área não existe para ninguém.
</details>

<details>
<summary><b>Leitura de comprovativos com IA (Google Gemini)</b></summary>

Totalmente opcional: sem chave tudo funciona, apenas a leitura automática fica desligada e os movimentos são registados manualmente.

1. Gere uma chave em <https://aistudio.google.com/apikey>.
2. **Ative a faturação** no projeto Google dessa chave. Segundo os termos da Google, o conteúdo enviado por uma chave sem faturação (nível gratuito) pode ser usado para melhorar os produtos deles; com a faturação ativa, não. Consulte os termos atuais antes de usar com dados reais.
3. No `docker-compose.yml`, preencha `GEMINI_API_KEY: "a-sua-chave"` e execute `docker compose up -d`.

**O que é enviado à Google:** apenas a imagem ou o PDF do comprovativo e a lista de categorias da aplicação, para a IA escolher uma. Saldos, contas, nomes e restantes movimentos **não** são enviados. A chave fica apenas no servidor.

**Como funciona:** a IA devolve uma *sugestão*; confere, corrige se necessário e só depois guarda. `CAPTURAS_POR_DIA` (predefinição 30) limita a utilização por pessoa e controla o custo.
</details>

<details>
<summary><b>Aceder fora de casa e instalar no telemóvel</b></summary>

A aplicação funciona em qualquer rede onde o computador esteja acessível; não depende de nenhum serviço externo. **Como expô-la à internet é uma escolha sua** (VPN, túnel, proxy inverso com HTTPS, o que preferir).

- Para **instalar no telemóvel** como aplicação, o navegador exige HTTPS (ou `localhost`). Sem HTTPS continua a poder usar a aplicação normalmente no navegador.
- Com HTTPS a aplicação marca o cookie de sessão como seguro automaticamente. Ajuste `APP_URL` para o endereço público, para que as ligações dos e-mails de convite funcionem.
- Se usar um proxy, encaminhe para a porta 8472 e envie os cabeçalhos `X-Forwarded-For` e `X-Forwarded-Proto`. Exemplo com Caddy (obtém o certificado sozinho): `financas.odominio.pt { reverse_proxy 127.0.0.1:8472 }`.
- Para aceitar ligações só do próprio computador (por exemplo, atrás de um proxy local), troque a linha `"8472:8472"` por `"127.0.0.1:8472:8472"` no `docker-compose.yml`.

> **Atenção:** qualquer pessoa que alcance o endereço pode criar uma conta (basta receber o código por e-mail), e a aplicação envia esses e-mails pela sua conta SMTP. Por isso, mantenha a aplicação na rede local ou proteja o acesso externo. A aplicação limita pedidos de código e de convite por pessoa, mas isso não substitui essa proteção.
</details>

<details>
<summary><b>Cópia de segurança e restauro</b></summary>

Os seus dados ficam em volumes do Docker (`pgdata`, a base de dados, e `dados`, os comprovativos). Eles **sobrevivem** a atualizações e reinícios.

> **Nunca execute `docker compose down -v`**: o `-v` apaga os volumes, ou seja, todos os seus dados. Para parar a aplicação use `docker compose stop` (ou `docker compose down`, sem `-v`).

**Fazer uma cópia de segurança** (no Windows, use o WSL ou o Git Bash: o PowerShell altera a codificação dos ficheiros gerados):

```bash
docker compose exec -T db pg_dump -U fin_owner -d financas -Fc > financas-$(date +%F).dump
docker compose exec -T api tar czf - -C /data . > comprovantes-$(date +%F).tgz
```

**Guarde esses ficheiros fora do computador** (outro disco, nuvem). Para automatizar, coloque os dois comandos no `crontab -e`, com `cd /pasta/do/docker-compose &&` antes.

**Restaurar** (numa instalação nova ou na mesma, depois de um problema):

```bash
docker compose up -d                  # a aplicação cria a estrutura vazia
docker compose stop api
docker compose exec -T db pg_restore -U fin_owner -d financas --clean --if-exists --no-owner < financas-AAAA-MM-DD.dump
docker compose exec -T api tar xzf - -C /data < comprovantes-AAAA-MM-DD.tgz     # comprovativos (opcional)
docker compose start api
```
</details>

<details>
<summary><b>Atualizar para uma versão nova</b></summary>

Faça uma cópia de segurança (acima) e, na pasta do `docker-compose.yml`:

```bash
docker compose pull
docker compose up -d
```

- Os seus dados não são tocados. As alterações à base de dados são aplicadas sozinhas no arranque e **apenas acrescentam**.
- O `docker-compose.yml` usa `:latest`, que acompanha sempre a versão mais recente. Antes de uma versão principal nova (a 2.0, por exemplo), leia o [CHANGELOG](CHANGELOG.md): pode exigir ação da sua parte. Para fixar uma versão, altere, por exemplo, para `:1.9.0` na linha `x-imagem`.
- Antes de atualizar, leia o [CHANGELOG](CHANGELOG.md): as alterações que exijam alguma ação sua estão destacadas aí. Em Mais → Sobre o aplicativo vê a versão em uso e as novidades; se o servidor for mais recente do que a aplicação aberta no telemóvel, aparece o botão para atualizar.
- **Voltar atrás:** restaure a cópia de segurança feita antes e use a versão anterior. Voltar apenas a imagem, sem restaurar a base de dados, pode não funcionar se a nova versão alterou a estrutura desta.
- Evite ferramentas de atualização automática (como o Watchtower): as alterações à base de dados acontecem no arranque, e uma cópia de segurança antes é importante.
</details>

## Problemas comuns

| Sintoma | O que fazer |
|---|---|
| A aplicação não arranca (o contentor `api` reinicia continuamente) | `docker compose logs api`: a primeira linha diz o que falta preencher. |
| O código não chega por e-mail | `docker compose logs api` e procure `e-mail enviado` ou `falha ao enviar`. Causas comuns: palavra-passe de aplicação errada, verificação em dois passos desligada, mensagem no spam. |
| Não abre noutro dispositivo da rede | Use `http://IP-DO-COMPUTADOR:8472` e permita a porta 8472 na firewall do computador. |
| A porta 8472 já está em uso | No `docker-compose.yml`, troque `"8472:8472"` por `"8080:8472"` e use a porta 8080. |
| Depois de atualizar, o telemóvel mostra o ecrã antigo | Mais → Sobre o aplicativo → atualizar; se não aparecer, limpe uma vez os dados do site no navegador do telemóvel. |
| A leitura de comprovativos não funciona | Confira `GEMINI_API_KEY` e se a faturação do projeto Google está ativa; o registo mostra o erro devolvido. |

## Privacidade e segurança

- Os dados ficam no seu servidor. Os únicos dados que saem dele são os que escolher enviar: os e-mails de código e convite (pelo seu fornecedor de SMTP) e, se ativar a leitura por IA, a imagem do comprovativo (para a Google).
- Cada pessoa só vê o que é seu ou o que foi partilhado consigo, e isso é imposto pela base de dados.
- Os segredos (palavras-passe da base de dados e chave de proteção dos códigos) são gerados automaticamente e guardados num volume próprio do Docker.
- Para comunicar uma falha de segurança, veja [SECURITY.md](SECURITY.md).

## Remover a instalação

Para desligar a aplicação mantendo os dados: `docker compose down`. Para **apagar tudo definitivamente** (base de dados, comprovativos e segredos): `docker compose down -v`. Só o faça com a certeza e com uma cópia de segurança guardada.

Cada pessoa pode também eliminar a própria conta e os próprios dados em Mais → Meu perfil → *Excluir minha conta e todos os meus dados*, com confirmação por código enviado para o e-mail. Se for titular de contas ou cartões partilhados, estes são apagados para todos, e a aplicação avisa antes quem perde o acesso.

## Para programadores

Tecnologias: Python 3.12 (FastAPI), PostgreSQL 16 com segurança ao nível da linha, interface em JavaScript puro (PWA, sem etapa de compilação). As migrações estão em `backend/migrations` e são aplicadas no arranque.

```bash
# executar a partir do código-fonte (compila a imagem localmente)
docker compose -f docker-compose.yml -f docker-compose.build.yml up -d --build

# testes (exigem um PostgreSQL local com o papel fin_owner e a base financas_test; veja backend/tests/conftest.py)
cd backend && pip install -r requirements-dev.txt && python -m pytest -q
```

Cada versão é uma etiqueta `vX.Y.Z` (o ficheiro `VERSION` tem de coincidir): ao criar a etiqueta, o GitHub Actions executa os testes e publica a imagem `ghcr.io/andregoncalvespires/financas`.

## Licença e aviso

Distribuído sob a **GNU Affero General Public License v3.0** ([LICENSE](LICENSE)). Em resumo: pode usar, estudar, modificar e partilhar o programa; se oferecer uma versão modificada como serviço a outras pessoas através da rede, tem de disponibilizar o código-fonte dela sob a mesma licença. Este resumo não substitui o texto da licença.

Este software é fornecido **no estado em que se encontra**, sem garantias, e não constitui aconselhamento financeiro. Mantenha cópias de segurança dos seus dados.
