# Diagramas de Fluxo do PixelLayer (Mermaid)

Este documento reúne os diagramas arquiteturais e comportamentais do **PixelLayer** (`img-cut`) expressos em formato **Mermaid**. Os diagramas cobrem a sequência cronológica completa, a topologia de componentes, a máquina de estados do ciclo de vida dos modelos (*Zero Idle / Lazy Loading*) e o fluxo encadeado de pipeline em lote.

---

## 1. Diagrama de Sequência Ponta a Ponta

Este diagrama detalha a troca de mensagens entre todos os módulos desde o disparo da ferramenta pelo Agente de IA até a entrega final do caminho relativo seguro e dos metadados.

```mermaid
sequenceDiagram
    autonumber
    actor Agente as Agente de IA (Client MCP)
    participant MCP as FastMCP Server (tools.py)
    participant Safe as SafePath Validator (files.py)
    participant Engine as Background Processor (background.py)
    participant Reg as ModelRegistry (registry.py)
    participant Wrap as Model Wrapper (base.py / birefnet.py)
    participant GPU as PyTorch / Torchvision (CUDA / CPU)
    participant Disk as Sistema de Arquivos (Disco Local)

    Note over Agente, MCP: 1. Disparo de Ferramenta via Stdio (Path-Only)
    Agente->>MCP: JSON-RPC Call: remove_background(image_path="input/foto.png", model="birefnet-general")

    Note over MCP, Safe: 2. Validação de Contrato & Sanitização de Caminho
    MCP->>Safe: resolve_safe_path("input/foto.png")
    Safe->>Disk: Verifica existência e confinamento no workspace
    Disk-->>Safe: Caminho absoluto validado
    Safe-->>MCP: Retorna caminho seguro validado

    Note over MCP, Engine: 3. Execução do Processador de Imagem
    MCP->>Engine: remove_background(resolved_path, model_id, output_format)
    Engine->>Disk: Image.open(resolved_path)
    Disk-->>Engine: PIL Image carregada (RGB)
    Engine->>Engine: Validação de limite de pixels (Max Pixels Check)

    Note over Engine, Wrap: 4. Resolução do Modelo & Lazy Loading
    Engine->>Reg: registry.get("birefnet-general")
    Reg-->>Engine: Retorna instância do BiRefNetModel
    Engine->>Wrap: model.predict(pil_image)

    Wrap->>Wrap: ensure_loaded() (Adquire threading.RLock)
    alt Modelo NÃO está em memória (Primeira chamada ou pós-TTL)
        Wrap->>Disk: Carrega pesos do cache local (models_cache/)
        Disk-->>Wrap: Pesos neurais lidos
        Wrap->>GPU: Aloca tensores na VRAM (ou RAM CPU)
        GPU-->>Wrap: Modelo pronto em modo eval()
    else Modelo já residente em memória (Warm)
        Wrap->>Wrap: Reaproveita instância existente
    end

    Wrap->>Wrap: Cancela timer anterior e agenda auto-unload (TTL = 300s)

    Note over Wrap, GPU: 5. Inferência Neural & Canal Alfa
    Wrap->>GPU: Pré-processamento (Resize 1024x1024, Normalize ImageNet, ToTensor)
    Wrap->>GPU: Inicia inferência protegida (torch.no_grad, ThreadPoolExecutor)
    GPU->>GPU: Processa tensores e extrai predição fina
    GPU->>GPU: Ativação Sigmoid [0.0, 1.0] -> Transfere para CPU
    GPU-->>Wrap: Retorna máscara binária/contínua em NumPy
    Wrap->>Wrap: Redimensiona máscara para tamanho original e aplica putalpha()
    Wrap-->>Engine: Retorna imagem PIL RGBA (Transparência pura de 32-bit)

    Note over Engine, Disk: 6. Persistência e Coleta de Metadados
    Engine->>Disk: Salva arquivo final (ex: output/foto_nobg.png) com optimize=True
    Disk-->>Engine: Arquivo gravado com sucesso
    Engine->>Disk: os.stat() para ler tamanho final em bytes
    Disk-->>Engine: Tamanho obtido
    Engine->>Safe: to_safe_relative_path(out_path)
    Safe-->>Engine: Retorna caminho relativo seguro (ex: "output/foto_nobg.png")
    Engine->>Engine: Constrói RemoveBackgroundOutput (Dimensões, Redução %, Tempo ms)
    Engine-->>MCP: Retorna objeto Pydantic validado

    Note over MCP, Agente: 7. Resposta Estruturada ao Agente
    MCP-->>Agente: JSON-RPC Result: {success: true, image: {file_path: "output/foto_nobg.png", ...}}
```

---

## 2. Topologia Arquitetural e Fluxo de Dados

Este diagrama visualiza a divisão das camadas lógicas, componentes internos e interfaces de proteção do sistema.

```mermaid
flowchart TD
    subgraph ClientLayer["1. Camada do Cliente / Agente de IA"]
        Agent["Agente de IA (Claude, Antigravity, Cursor)"]
    end

    subgraph TransportLayer["2. Transporte & Protocolo MCP"]
        StdioChannel["Transporte Stdio (JSON-RPC)"]
        FastMCPServer["Servidor FastMCP (src/mcp_server/tools.py)"]
        PydanticContracts["Contratos Pydantic v2 (src/contracts/schemas.py)"]
    end

    subgraph SecurityLayer["3. Isolamento & Segurança (Sandbox)"]
        SafePathResolve["resolve_safe_path() (Validação Anti-Traversal)"]
        WorkspaceConfig["Workspaces Autorizados (PIXELLAYER_ALLOWED_WORKSPACES)"]
        SafePathRelative["to_safe_relative_path() (Sanitização de Retorno)"]
    end

    subgraph EngineLayer["4. Engine de Processamento de Imagens"]
        ProcessorDispatcher{"Despachante de Processadores"}
        BgProcessor["Background Processor (src/engine/processors/background.py)"]
        ConvProcessor["Converter Processor (src/engine/processors/converter.py)"]
        ResizeProcessor["Resizer Processor (src/engine/processors/resizer.py)"]
        OptProcessor["Optimizer Processor (src/engine/processors/optimizer.py)"]
        BatchPipeline["Pipeline Orchestrator (src/engine/pipeline.py)"]
    end

    subgraph ModelLayer["5. Gerenciamento de Modelos & Hardware"]
        ModelReg["Model Registry (Singleton)"]
        BaseModelWrapper["BaseModel Wrapper (Thread-Safe RLock)"]
        TTLTimer["Temporizador de Descarga TTL (300s)"]
        BiRefNetEngine["Wrapper BiRefNet / RMBG / IS-Net"]
        PyTorchCUDA["PyTorch / Torchvision (Device: CUDA ou CPU)"]
    end

    subgraph StorageLayer["6. Armazenamento Local"]
        InputFiles["Imagens de Entrada (Workspace)"]
        LocalCache["Cache de Pesos Neurais (models_cache/)"]
        OutputFiles["Imagens Processadas (output/...)"]
        LogDir["Logs da Aplicação (logs/pixellayer.log)"]
    end

    %% Conexões do Fluxo Principal
    Agent -->|"Chamada de ferramenta (Path-Only)"| StdioChannel
    StdioChannel --> FastMCPServer
    FastMCPServer --> PydanticContracts
    PydanticContracts --> SafePathResolve
    SafePathResolve -.->|"Checa limites"| WorkspaceConfig
    SafePathResolve -->|"Carrega arquivo seguro"| InputFiles

    SafePathResolve --> ProcessorDispatcher
    ProcessorDispatcher -->|"remove_background"| BgProcessor
    ProcessorDispatcher -->|"convert_format"| ConvProcessor
    ProcessorDispatcher -->|"resize_image"| ResizeProcessor
    ProcessorDispatcher -->|"optimize_image"| OptProcessor
    ProcessorDispatcher -->|"batch_process"| BatchPipeline

    BgProcessor -->|"Solicita modelo"| ModelReg
    ModelReg --> BaseModelWrapper
    BaseModelWrapper -->|"Lazy Load / Cache"| LocalCache
    BaseModelWrapper -->|"Gerencia vida útil"| TTLTimer
    BaseModelWrapper --> BiRefNetEngine
    BiRefNetEngine -->|"Inferência no_grad()"| PyTorchCUDA
    PyTorchCUDA -->|"Retorna máscara alfa"| BgProcessor

    BgProcessor -->|"Salva imagem RGBA"| OutputFiles
    BgProcessor --> SafePathRelative
    SafePathRelative --> FastMCPServer
    FastMCPServer -->|"Registra auditoria"| LogDir
    FastMCPServer -->|"Retorna metadados JSON (Path-Only)"| StdioChannel
    StdioChannel --> Agent
```

---

## 3. Máquina de Estados: Ciclo de Vida dos Modelos (Zero Idle)

Este diagrama representa o ciclo de vida dos modelos neurais em memória. Mostra como o sistema mantém **recursos ociosos nulos** no arranque do servidor e descarrega automaticamente os pesos após inatividade.

```mermaid
stateDiagram-v2
    [*] --> DESCARREGADO : Inicialização do Servidor MCP (<1s)

    DESCARREGADO --> CARREGANDO : Primeira chamada de inferência (predict)
    note right of DESCARREGADO
        Servidor inicia instantaneamente.
        Nenhum peso na VRAM/RAM.
        list_models() não carrega pesos.
    end note

    CARREGANDO --> PRONTO_EM_MEMORIA : Pesos alocados na VRAM (CUDA) ou RAM (CPU)
    note right of CARREGANDO
        Leitura de models_cache/
        AutoModelForImageSegmentation
        model.eval()
    end note

    PRONTO_EM_MEMORIA --> EM_INFERENCIA : Processando imagem
    EM_INFERENCIA --> PRONTO_EM_MEMORIA : Inferência finalizada com sucesso

    state PRONTO_EM_MEMORIA {
        [*] --> TIMER_INICIADO
        TIMER_INICIADO --> CONTAGEM_REGRESSIVA : threading.Timer (TTL = 300s)
        CONTAGEM_REGRESSIVA --> TIMER_RENOVADO : Nova requisição chega antes do tempo
        TIMER_RENOVADO --> CONTAGEM_REGRESSIVA : Reinicia contador de 300 segundos
    }

    PRONTO_EM_MEMORIA --> DESCARREGANDO : Inatividade atinge 300s (TTL Expirado)
    DESCARREGANDO --> DESCARREGADO : Executa unload() & torch.cuda.empty_cache()

    note left of DESCARREGADO
        Memória de vídeo e RAM
        são devolvidas ao sistema operacional.
    end note
```

---

## 4. Diagrama de Fluxo do Pipeline em Lote (`batch_process`)

Quando o cliente solicita a execução sequencial encadeada de múltiplos passos em uma única invocação, o pipeline orquestra a saída de um processador como entrada do próximo, limpando arquivos intermediários automaticamente.

```mermaid
flowchart LR
    StartFile["Arquivo de Entrada (ex: raw.jpg)"] --> Step1["Passo 1: remove_background (BiRefNet)"]
    Step1 -->|"Gera intermediário 1 (.png)"| Step2["Passo 2: resize_image (Modo fit/Lanczos)"]
    Step2 -->|"Gera intermediário 2 (.png)"| Step3["Passo 3: convert_format (Para WebP)"]
    Step3 -->|"Gera intermediário 3 (.webp)"| Step4["Passo 4: optimize_image (Medium preset)"]

    Step4 --> FinalFile["Arquivo Final de Entrega (ex: output/raw_nobg_resized.webp)"]

    subgraph Cleanup["Limpeza Automática"]
        Step1 -.->|"Limpa temp 1"| GarbageCollector["Remoção de Arquivos Intermediários"]
        Step2 -.->|"Limpa temp 2"| GarbageCollector
        Step3 -.->|"Limpa temp 3"| GarbageCollector
    end
```
