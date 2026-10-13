# MT em Dados

Programa que roda no seu computador e, todo dia:

1. baixa dados públicos de Mato Grosso (INPE, IBGE, diários oficiais, clima);
2. monta as artes (feed, carrossel, story e reel) em estilo de infográfico de jornal;
3. escreve as legendas (com o Claude da sua assinatura, ou com modelos prontos);
4. coloca tudo numa **fila de revisão** para você aprovar, editar ou rejeitar;
5. publica no Instagram, no horário marcado, em uma ou várias contas.

Nada é publicado sem passar pela sua aprovação, a não ser que você ligue a aprovação automática em uma conta.

---

## 1. Instalar (Windows)

1. Instale o **Python 3.12 ou mais novo**: https://www.python.org/downloads/
   Na primeira tela do instalador, marque **"Add python.exe to PATH"**.
2. Copie a pasta `mt-dados-insta` para onde quiser (ex.: `Documentos`).
3. Dê dois cliques em **`iniciar.bat`**.
   Na primeira vez ele prepara tudo (leva alguns minutos). Depois abre o painel no navegador em `http://127.0.0.1:8765`.

A janela preta precisa ficar aberta: é ela que gera e publica nos horários. Se fechar, os posts aprovados saem quando você abrir de novo.

> Mac/Linux: rode `./iniciar.sh` no terminal.

## 2. Ligar o Claude pela sua assinatura Pro (sem custo extra)

O programa usa o **Claude Code**, o comando `claude` do terminal, logado na sua conta Pro.

No **PowerShell**:

```powershell
irm https://claude.ai/install.ps1 | iex
```

Feche e abra o PowerShell, e rode:

```powershell
claude
```

Ele abre o navegador para você entrar com a conta do Claude (a mesma do plano Pro). Depois de logado, pode fechar com `/exit`.

No painel, em **Configurações → Claude**:
- marque "Usar o Claude para escrever as legendas";
- deixe "Minha assinatura (Claude Code)" selecionado;
- clique em **Testar o Claude**.

**Proteções que o programa aplica:**
- Antes de cada chamada, confere com `claude auth status` que o login é da assinatura. Se o Claude Code estiver usando uma chave de API (que gera cobrança), a chamada é **bloqueada**.
- Remove as variáveis `ANTHROPIC_API_KEY` e parecidas do processo, para não haver cobrança por engano.
- Roda o Claude numa pasta vazia, sem ferramentas: ele não lê nem mexe em nada do seu computador.
- **Teto de tokens por dia e por mês**, que você define. Antes de cada chamada ele reserva a estimativa e recusa se passar do teto. Quando acaba, os posts continuam saindo com os textos-modelo.
- Se o Claude escrever qualquer número que não está nos dados, o texto dele é descartado.

O uso entra no limite do seu plano Pro, o mesmo que você usa no chat. Por isso o padrão é o modelo **Haiku**, que gasta menos. Cada legenda consome cerca de 1.000 a 1.500 tokens.

## 3. Conectar o Instagram

Você precisa de uma conta **profissional do tipo Empresa** (Configurações do Instagram → Tipo de conta → Mudar para conta profissional → Empresa). Conta de criador não publica story pela API.

1. Entre em https://developers.facebook.com, clique em **Meus apps → Criar app**, escolha o caso de uso de **Instagram** (gerenciar mensagens e conteúdo).
2. No painel do app, vá em **Instagram → Configuração da API com login do Instagram**.
3. Em **Gerar tokens de acesso**, clique em **Adicionar conta** e entre com o Instagram que vai receber os posts. Dê as permissões `instagram_business_basic` e `instagram_business_content_publish`.
4. Copie o **token** gerado.
5. No painel do programa: **Contas do Instagram → Nova conta**, cole o token, salve e clique em **Testar conexão**. O ID da conta é preenchido sozinho.

Enquanto o app da Meta estiver em modo de desenvolvimento, ele só publica nas contas que você adicionou no passo 3, o que é exatamente o caso aqui. O token vale 60 dias e o programa renova sozinho quando faltam 15.

**Várias contas:** repita o processo para cada Instagram. Cada conta tem seus horários, pautas, cor e, se quiser, municípios em foco (ex.: uma conta só de Cuiabá com o código `5103403`).

## 4. Hospedagem das imagens (Cloudinary, grátis)

O Instagram só aceita mídia por link público. O programa envia a imagem, publica e apaga em seguida.

1. Crie uma conta gratuita em https://cloudinary.com
2. No painel do Cloudinary, copie **Cloud name**, **API Key** e **API Secret**.
3. Cole em **Configurações → Hospedagem** e clique em **Testar hospedagem**.

Alternativa sem Cloudinary: o modo "Meu próprio túnel" serve só a pasta de mídia na porta 8766. Exponha **apenas essa porta** com um túnel (ex.: Cloudflare Tunnel). Nunca exponha a porta 8765, que é o painel.

## 5. Uso no dia a dia

- Às 05:00 (ajustável) o programa gera a pauta de cada conta. Se o PC estava desligado, gera quando você abrir.
- Abra **Revisão**: para cada post, olhe a arte, leia a legenda e confira a caixa **"Dados usados"**.
- Avisos em amarelo apontam expressões com cara de IA, frases longas, travessões etc.
- **Salvar e aprovar** leva direto ao próximo post para revisar.
- **Reescrever com o Claude** aceita um pedido ("mais curta", "comece pelo município") e mostra quantos tokens vai gastar.
- Posts de **diário oficial** sempre exigem sua revisão e trazem o link do documento original.

### Pautas disponíveis

| Pauta | Formato | Fonte | Atualização |
|---|---|---|---|
| Queimadas do dia | feed + story | INPE, Programa Queimadas (satélite de referência AQUA_M-T) | diária |
| Tempo do dia | story | Open-Meteo (previsão) | diária |
| Município do dia | carrossel | IBGE (Censo 2022, PIB dos Municípios) | rodízio pelos 141 municípios |
| Município do dia | reel | IBGE | rodízio |
| Rankings | feed | IBGE | alterna a métrica por dia |
| Diário oficial | feed | Querido Diário (Open Knowledge Brasil) | diária, onde houver cobertura |
| Sua agenda | feed | arquivo `dados/agenda.csv` | nas datas que você cadastrar |

Com tudo ligado, saem de 6 a 8 posts por dia por conta. Se faltar pauta, o programa completa o mínimo (5, ajustável) com rankings.

### Fotos reais (opcional)

Para a capa do "Município do dia" usar uma foto de verdade em vez do mapa, crie a pasta `dados/fotos/<código IBGE>/` e coloque a foto lá (sua ou com licença de uso). Se quiser crédito na arte, crie `credito.txt` na mesma pasta com o nome do fotógrafo. Ex.: `dados/fotos/5103403/` para Cuiabá.

O programa **não gera foto nem ilustração por IA**. As imagens são o próprio dado: mapa, número, gráfico.

### Agenda própria

Edite `dados/agenda.csv` (abre no Excel). Formato:

```
data;titulo;texto;fonte
08/04;Aniversário de Cuiabá;Cuiabá foi fundada em 8 de abril de 1719, às margens do rio Cuiabá.;Prefeitura de Cuiabá
```

`DD/MM` repete todo ano; `DD/MM/AAAA` vale só naquele dia.

## 6. Abrir sozinho quando o Windows liga

1. Aperte `Win + R`, digite `shell:startup` e dê Enter.
2. Crie ali um atalho para o `iniciar.bat`.

O computador precisa estar ligado e com o programa aberto nos horários de publicação.

## 7. Cuidados

- **Período eleitoral:** estamos entre o 1º e o 2º turno. O Claude está instruído a não opinar sobre governos, prefeitos ou partidos, mas a revisão final é sua.
- **Perfil independente:** não use brasão, logo ou nome que pareça perfil oficial do governo.
- **Foco de calor não é incêndio.** As legendas já explicam isso. A contagem usa o mesmo satélite de referência do INPE; quando ele não passa, o post avisa qual satélite foi usado.
- **Querido Diário** não cobre todos os municípios de MT; quando não houver resultado, a pauta é pulada.
- Os Reels saem sem música, de propósito: trilhas com direitos autorais derrubam o post. Se quiser, adicione áudio do próprio Instagram depois de publicado.

## Onde ficam as coisas

```
iniciar.bat            abre o programa (Windows)
dados/app.db           banco local (posts, contas, uso do Claude)
dados/.chave           chave que criptografa os tokens; não compartilhe
dados/midia/           artes geradas, por dia e por conta
dados/fotos/           suas fotos reais para capas (opcional)
dados/agenda.csv       suas datas
app/                   código (Python + FastAPI)
fontes/                Inter e Lora (licença SIL Open Font)
```

Para fazer backup, copie a pasta `dados/` inteira.

Malha municipal de reserva (usada sem internet): derivada da malha do IBGE, via projeto geodata-br.
