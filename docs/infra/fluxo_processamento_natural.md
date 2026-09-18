# Fluxo de Processamento do PixelLayer (Linguagem Natural)

Este documento descreve detalhadamente, em linguagem natural e estrutura arquitetural descritiva, todo o ciclo de vida de uma requisição no **PixelLayer** (`img-cut`). O fluxo compreende desde a intenção do Modelo/Agente de IA cliente, passando pela camada de protocolo MCP, validação de contratos, isolamento de segurança, ciclo de vida dos modelos de visão computacional, inferência neural, persistência em disco, até a entrega final dos metadados e imagem processada.

---

## 1. Visão Geral dos Participantes

| Componente | Papel Arquitetural | Módulo no Código |
|---|---|---|
| **Agente Consumidor** | Modelo/Agente de IA (Claude, Antigravity, Cursor, etc.) que decide acionar a ferramenta via JSON-RPC. | Cliente MCP Externo |
| **Transporte MCP (stdio)** | Canal de comunicação bidirecional via entrada e saída de erro padrão (`stdio`/`stderr`), reservando `stdout` exclusivamente para pacotes MCP. | FastMCP / Stdio Transport |
| **FastMCP Server & Ferramentas** | Ponto de entrada que decodifica parâmetros e garante tipagem estrita de I/O. | `src/mcp_server/tools.py` |
| **Contratos & Schemas** | Validação sintática e semântica com Pydantic v2. | `src/contracts/schemas.py` |
| **Módulo de Segurança (SafePath)** | Garante confinamento (*sandbox*) dentro dos workspaces autorizados e impede *path traversal*. | `src/utils/files.py` |
| **Engine de Processamento** | Orquestrador de alto nível da operação (ex: remoção de fundo, conversão, resize). | `src/engine/processors/` |
| **Model Registry** | Gerenciador singleton que indexa modelos sem alocar memória e controla o ciclo de vida. | `src/engine/models/registry.py` |
| **Wrapper do Modelo (BaseModel)** | Controlador de concorrência com carregamento sob demanda (*lazy-load*) e *timer* de descarga (TTL). | `src/engine/models/base.py` |
| **Rede Neural / PyTorch** | Motor de inferência (BiRefNet, RMBG, IS-Net) executado em GPU (CUDA) ou CPU. | `src/engine/models/birefnet.py` |
| **Sistema de Arquivos** | Armazenamento persistente local (leitura do arquivo original e escrita do resultado final). | Disco Local / Workspace |

---

## 2. Representação Visual em Blocos de Texto

```
[ Agente de IA / Modelo Cliente ]
               │
               ▼ 1. Envia JSON-RPC via stdio (ex: remove_background)
[ FastMCP Server (src.mcp_server.tools) ]
               │
               ▼ 2. Valida tipos e enums (Pydantic v2)
[ Módulo de Validação & Contratos (src.contracts) ]
               │
               ▼ 3. Sanitiza e confina o caminho do arquivo (resolve_safe_path)
[ Módulo de Segurança de Arquivos (src.utils.files) ]
               │
               ▼ 4. Delega para o processador de negócio
[ Background Processor (src.engine.processors.background) ]
               │
               ├── Leitura da imagem original e checagem de limites (PIL.Image)
               │
               ▼ 5. Solicita instância do modelo neural
[ Model Registry (src.engine.models.registry) ]
               │
               ▼ 6. Verifica se o modelo já está carregado em memória
[ Wrapper do Modelo (src.engine.models.base) ]
        ├── SE NÃO CARREGADO:
        │     Carrega pesos do cache local para GPU/CPU (AutoModelForImageSegmentation)
        └── SE CARREGADO:
              Renova o temporizador de ociosidade (TTL de 300s)
               │
               ▼ 7. Pré-processamento, Inferência e Pós-processamento
[ Rede Neural BiRefNet / PyTorch (src.engine.models.birefnet) ]
        ├── Resize para 1024x1024 & Normalização ImageNet
        ├── Inferência assíncrona/protegida (torch.no_grad())
        ├── Ativação Sigmoid para máscara probabilística [0, 1]
        └── Composição RGBA (RGB original + Canal Alfa gerado)
               │
               ▼ 8. Persistência em disco (PNG/WebP otimizado)
[ Sistema de Arquivos Local (output/...) ]
               │
               ▼ 9. Conversão do caminho absoluto para caminho relativo seguro
[ to_safe_relative_path (src.utils.files) ]
               │
               ▼ 10. Retorno estruturado (Path-Only: sem base64)
[ Agente de IA / Modelo Cliente ]
```

---

## 3. O Fluxo Detalhado Passo a Passo

### Fase 1: Disparo da Requisição pelo Agente de IA
1. O Agente de IA identifica a necessidade de manipular uma imagem (por exemplo, remover o fundo de uma foto de produto).
2. O agente constrói uma mensagem JSON-RPC especificando o nome da ferramenta (`remove_background`) e os argumentos em texto:
   - `image_path`: `"input/produto.png"` (caminho relativo ao workspace).
   - `model`: `"birefnet-general"` (opcional, padrão).
   - `output_format`: `"png"` (opcional).
3. **Regra Path-Only**: Em hipótese alguma o agente envia o arquivo binário ou string base64. Apenas o endereço textual do arquivo no workspace é transmitido.
4. A mensagem é enviada pelo canal de transporte padrão `stdio`.

### Fase 2: Recepção MCP e Validação de Contrato
1. O servidor FastMCP (`src/mcp_server/tools.py`) intercepta o evento JSON-RPC.
2. Os argumentos são submetidos aos esquemas definidos em `src/contracts/schemas.py`:
   - O formato de saída é validado contra o Enum `ImageFormat` (`png`, `webp`, `jpeg`).
   - Se os parâmetros forem inválidos, uma resposta estruturada de erro é imediatamente devolvida, abortando o processamento antes de tocar em recursos pesados.

### Fase 3: Sanitização de Caminhos e Blindagem Contra Traversal
1. O servidor repassa a string `image_path` para a função `resolve_safe_path()` (`src/utils/files.py`).
2. A função analisa o caminho:
   - Se for relativo, resolve primeiro contra o diretório de trabalho corrente (`cwd`) e depois contra a lista de workspaces permitidos (`PIXELLAYER_ALLOWED_WORKSPACES`).
   - Converte o caminho em um caminho absoluto normalizado (`Path.resolve()`).
   - **Checagem de Isolamento**: Valida se o caminho resultante está contido dentro dos diretórios autorizados (`p.is_relative_to(ws)`).
   - Se houver tentativa de invasão (como `../../etc/passwd`), lança imediatamente uma exceção `SecurityError` (código `PATH_TRAVERSAL_DETECTED`).
   - Verifica se o arquivo físico realmente existe no disco. Se inexistente, lança `FileNotFoundError_`.
3. Se um `output_path` não for especificado pelo cliente, a função `generate_output_path()` calcula automaticamente o caminho de destino no mesmo diretório ou na pasta autorizada (ex: `input/produto_nobg.png`).

### Fase 4: Orquestração do Processador de Imagem
1. O fluxo entra no processador de domínio `src/engine/processors/background.py` na função `remove_background()`.
2. É iniciada a medição de tempo de execução (`time.monotonic()`).
3. O processador verifica a extensão do arquivo contra os formatos suportados (`.png`, `.jpg`, `.jpeg`, `.webp`, `.bmp`, `.tiff`).
4. O arquivo de imagem é aberto em memória com a biblioteca Pillow (`Image.open()`).
5. **Proteção Contra Decompression Bomb**: Calcula-se o total de pixels (`width * height`). Se exceder `config.MAX_IMAGE_PIXELS`, aborta com `ProcessingError` para evitar esgotamento de memória RAM.

### Fase 5: Ciclo de Vida do Modelo de IA (Lazy Loading e TTL)
1. O processador solicita a instância do modelo ao registro global: `registry.get(model_id)`.
2. O `ModelRegistry` localiza o wrapper correspondente (`BiRefNetModel`) sem ter carregado nada na inicialização do servidor (inicialização com *Zero Idle Memory*).
3. O método `model.predict()` é acionado e chama `self.ensure_loaded()`:
   - **Caso 1 (Primeira execução ou após expiração)**:
     - Adquire uma trava segura de thread (`threading.RLock`).
     - Identifica o hardware disponível através de `config.get_device()` (prioriza `cuda`, depois `cpu`).
     - Carrega os pesos da rede neural a partir do cache local `models_cache/` através do HuggingFace `AutoModelForImageSegmentation`.
     - Move o modelo para a GPU/CPU e configura modo de avaliação (`model.eval()`).
   - **Caso 2 (Modelo já aquecido / Warm)**:
     - Reaproveita a instância já residente na memória de vídeo (VRAM) ou RAM.
4. **Renovação do Temporizador TTL**:
   - Qualquer temporizador de descarga anterior é cancelado.
   - Um novo `threading.Timer` daemon é programado para `config.MODEL_TTL_SECONDS` (padrão de 300 segundos / 5 minutos).
   - Se o servidor ficar 5 minutos ocioso sem novas requisições de recorte, a função `unload()` será chamada em segundo plano, liberando a VRAM com `torch.cuda.empty_cache()`.

### Fase 6: Pipeline de Inferência Neural e Criação do Canal Alfa
1. A inferência é despachada dentro de um `ThreadPoolExecutor` protegido pelo tempo limite configurado em `config.INFERENCE_TIMEOUT`.
2. **Pré-processamento Tensor**:
   - A imagem original é convertida para o espaço de cor RGB e suas dimensões originais `(width, height)` são salvas.
   - É aplicada a pipeline de transformações Torchvision:
     1. Redimensionamento bilinear para o tamanho canônico da rede (`1024x1024`).
     2. Conversão para tensor PyTorch (`ToTensor()`).
     3. Normalização estatística padrão ImageNet (`mean=[0.485, 0.456, 0.406]`, `std=[0.229, 0.224, 0.225]`).
     4. Adição da dimensão de batch (`unsqueeze(0)`) e envio para o dispositivo acelerador (`to(device)`).
3. **Inferência da Rede**:
   - Executada sob o contexto `torch.no_grad()` para desabilitar o grafo de gradientes e otimizar memória.
   - A rede processa os tensores e retorna predições multi-escala; a predição final de maior fidelidade é selecionada.
   - Aplica-se a função matemática `torch.sigmoid()` para converter os valores brutos em probabilidades contínuas entre `0.0` (fundo) e `1.0` (objeto principal).
4. **Pós-processamento e Canal Alfa Perfeito**:
   - O tensor da máscara é transferido de volta para a memória da CPU (`cpu()`).
   - É convertido para uma matriz bidimensional NumPy e reescalado para valores de 8 bits inteiros (`0` a `255`).
   - A máscara é convertida em uma imagem PIL monocromática (`mode="L"`) e reamostrada com interpolação bilinear de volta para as dimensões exatas da imagem original.
   - Uma nova imagem **RGBA de 32 bits** é gerada: os canais de cor RGB originais são mantidos intactos, e a máscara gerada pela IA é aplicada como o canal de transparência alfa (`rgba.putalpha(mask_pil)`). Não há preenchimento (*fill*) branco ou preto.

### Fase 7: Gravação em Disco e Extração de Metadados
1. A pasta de destino é criada automaticamente se não existir (`ensure_parent_dir()`).
2. A imagem resultante é gravada fisicamente em disco de acordo com o formato solicitado:
   - Se `PNG`: Gravado com compressão otimizada sem perdas (`optimize=True`).
   - Se `WEBP`: Gravado com suporte a canal alfa e qualidade configurada.
   - Se `JPEG`: Como o JPEG não suporta canal alfa, o sistema emite um aviso no log e salva automaticamente como PNG para não destruir o recorte transparente.
3. O processador calcula as métricas do resultado:
   - Tamanho final em bytes e formato legível para humanos.
   - Diferença de peso e percentual de redução em relação à imagem original (`calculate_reduction`).
   - Tempo total transcorrido em milissegundos (`processing_time_ms`).

### Fase 8: Resposta ao Cliente MCP (Path-Only)
1. O caminho absoluto do arquivo salvo no disco é convertido para um caminho relativo seguro através de `to_safe_relative_path()`. Isso impede que nomes de diretórios internos do hospedeiro vazem para o agente de IA.
2. É instanciado o modelo Pydantic `RemoveBackgroundOutput`, contendo:
   - `success`: `true`
   - `image.file_path`: `"input/produto_nobg.png"`
   - `image.format`: `"png"`
   - `image.width`: `1920`
   - `image.height`: `1080`
   - `image.file_size_bytes`: `1458230`
   - `image.file_size_human`: `"1.39 MB"`
   - `model_used`: `"birefnet-general"`
   - `processing_time_ms`: `420`
   - `reduction_percent`: `-15.4`
3. O FastMCP serializa o resultado em JSON e envia via `stdio` de volta para o Agente de IA.
4. O Agente de IA recebe a confirmação imediata e pode prosseguir com o fluxo de trabalho (ex: exibir o arquivo para o usuário ou encadear uma nova edição).

---

## 4. Matriz de Tratamento de Falhas e Resiliência

| Ponto de Falha | Exceção Levantada | Código de Erro MCP | Ação de Recuperação / Resposta |
|---|---|---|---|
| Arquivo de entrada inexistente | `FileNotFoundError_` | `FILE_NOT_FOUND` | Retorna erro descritivo ao agente sem tentar carregar o modelo. |
| Caminho tenta acessar raiz do sistema | `SecurityError` | `PATH_TRAVERSAL_DETECTED` | Bloqueio imediato antes do acesso ao disco; registra auditoria em log. |
| Formato de arquivo não suportado | `UnsupportedFormatError` | `UNSUPPORTED_FORMAT` | Informa formatos aceitos (`.png`, `.jpg`, `.webp`, etc.). |
| Imagem excessivamente grande | `ProcessingError` | `PROCESSING_ERROR` | Impede estouro de memória (*OOM*) antes de decodificar o bitmap. |
| Tempo de inferência excede limite | `TimeoutError_` | `TIMEOUT_ERROR` | Interrompe a execução na GPU e cancela a thread de predição. |
| Falha ao baixar pesos do HuggingFace | `ModelLoadingError` | `MODEL_LOAD_FAILED` | Se `FORCE_LOCAL_FILES` estiver ativo, tenta fallback com mensagem clara. |
