from gradio.components.multimodal_textbox import MultimodalData
from gradio.components.chatbot import FileMessage
from gradio.data_classes import FileData
from gradio import ChatMessage
from typing import Generator

import gradio as gr
import subprocess
import ollama
import json
import os

SPACE: str = os.path.dirname(os.path.abspath(__file__))
SCRIPT_PATH: str = os.path.join(SPACE, "script.js")
CONFIG_PATH: str = os.path.join(SPACE, "config.json")
HISTORY_PATH: str = os.path.join(SPACE, "log")

# ================ Launch the Ollama Server ================ #
subprocess.run(["ollama", "list"], stdout=subprocess.DEVNULL)
# ========================================================== #

LOAD_HISTORY: list[dict] = []
"""workaround for loading history"""

LAST_USED_MODEL: str = None
"""pass into keep_alive to unload"""

with open(SCRIPT_PATH, "r", encoding="utf-8") as script:
    JS: str = script.read()

with open(CONFIG_PATH, "r", encoding="utf-8") as config:
    CONFIG: dict = json.load(config)


def list_models() -> list[str]:
    """List all locally available models"""
    models: list[ollama.ListResponse.Model] = ollama.list().models
    return [model.model for model in models]


def pull_model(model: str):
    """Download selected model"""
    try:
        gr.Info(f'Downloading "{model}"...')
        ollama.pull(model)
        gr.Info(f'Model "{model}" is ready!')
    except ollama._types.ResponseError:
        raise gr.Error(f'Failed to download model "{model}"...')


def unload_model(log: bool = True):
    """Free the memory occupied by model"""
    if LAST_USED_MODEL is not None:
        ollama.generate(model=LAST_USED_MODEL, prompt="", keep_alive=0)
        if log:
            gr.Info(f'Unloaded "{LAST_USED_MODEL}"...')


def load_configs() -> tuple[list[str], str, str, str, int]:
    """Load the local config"""
    all_models: list[str] = list_models()
    default_tab: str = CONFIG.get("default_tab", "opt")
    default_keep_alive: str = CONFIG.get("keep_alive", "5m")
    default_history_depth: int = CONFIG.get("history_depth", 8)
    default_model: str = CONFIG.get("default_model", None)
    model: str = (
        None
        if not all_models
        else (default_model if default_model in all_models else all_models[0])
    )

    return (all_models, model, default_tab, default_keep_alive, default_history_depth)


def save_configs(mdl: str, tab: str, keep: str, depth: float):
    """Save the config to disk"""
    try:
        CONFIG["default_model"] = mdl
        CONFIG["default_tab"] = tab
        CONFIG["keep_alive"] = keep
        CONFIG["history_depth"] = int(depth)
        with open(CONFIG_PATH, "w", encoding="utf-8") as file:
            json.dump(CONFIG, file)

        gr.Info("Config Saved!")
    except:
        raise gr.Error("Failed to save config...")


def list_history() -> list[str]:
    """List all chat logs on disk"""
    os.makedirs(HISTORY_PATH, exist_ok=True)
    return os.listdir(HISTORY_PATH)


def load_history(path: str) -> list[dict]:
    """Save the chat log from disk"""
    global LOAD_HISTORY
    with open(
        os.path.join(HISTORY_PATH, path if path.endswith(".json") else f"{path}.json"),
        encoding="utf-8",
        mode="r",
    ) as file:
        LOAD_HISTORY = json.load(file)
        return LOAD_HISTORY


def save_history(path: str, history: list[dict], save_metadata=False):
    """Save the chat log to disk"""
    if not save_metadata:
        for item in history:
            item.pop("metadata", None)
    try:
        with open(
            os.path.join(
                HISTORY_PATH, path if path.endswith(".json") else f"{path}.json"
            ),
            encoding="utf-8",
            mode="w+",
        ) as file:
            json.dump(history, file, separators=(",", ":"))

        gr.Info("History Saved!")
    except:
        raise gr.Error("Failed to save History...")


def _handle_file(query: str, file_path: str, file_type: str) -> tuple[str, list[str]]:
    """Process the uploaded file"""

    if "text" in file_type:
        with open(file_path, "r", encoding="utf-8") as f:
            data = f.read()
        query = f"{query}\n\n```\n{data}\n```"
        return (query, None)

    if "image" in file_type:
        return (query, [file_path])

    for T in ("json", "yaml", "xml"):
        if file_path.endswith(T):
            with open(file_path, "r", encoding="utf-8") as f:
                data = f.read()
            query = f"{query}\n\n```{T}\n{data}\n```"
            return (query, None)

    if file_path.endswith("pdf"):
        raise gr.Error("PDF is currently not supported...")
    elif bool(file_type):
        raise gr.Error(f'Unsupported File Type: "{file_type}"...')
    else:
        raise gr.Error("Unrecognized File Type...")


def chat(
    message: MultimodalData, history: list[ChatMessage], model: str
) -> Generator[str, None, None]:

    if model is None or not isinstance(model, str) or not model.strip():
        raise gr.Error("No Model Selected...")

    query: str = message.text
    files: list[FileData] = message.files

    multi_modal: bool = len(files) > 0

    if not multi_modal and not query.strip():
        raise gr.Error("Inputs are Empty...")

    if multi_modal:
        if len(files) > 1:
            gr.Warning(
                """Multi-files is not supported...
                (using the first file in this message)"""
            )

        file: FileData = files[0]
        file_path: str = file.path
        file_type: str = file.mime_type
        query, images = _handle_file(query, file_path, file_type)

    if len(LOAD_HISTORY) > 0:
        while history:
            history.pop()
        while LOAD_HISTORY:
            history.append(LOAD_HISTORY.pop(0))

    pruned_history: list[dict] = [
        msg for msg in history if not isinstance(msg["content"], FileMessage)
    ]

    messages: list[dict] = pruned_history[-CONFIG.get("history_depth", 8) :]
    messages.append({"role": "user", "content": query})

    if multi_modal and images:
        messages[-1].update({"images": images})

    global LAST_USED_MODEL
    if LAST_USED_MODEL != model:
        unload_model(False)
        LAST_USED_MODEL = model

    response = ""
    for part in ollama.chat(
        model=model,
        messages=messages,
        stream=True,
        keep_alive=CONFIG.get("keep_alive", "5m"),
    ):
        response += str(part["message"]["content"])
        yield response


with gr.Blocks(analytics_enabled=False, css="../style.css").queue() as block:
    all_models, default_model, default_tab, keep_alive, history_depth = load_configs()

    with gr.Tabs(selected=default_tab):
        with gr.Tab(label="Options", id="opt"):
            with gr.Accordion("Models", open=True):
                with gr.Row():
                    model = gr.Dropdown(
                        label="Current Model",
                        value=default_model,
                        choices=all_models,
                    )
                    mdl_name = gr.Textbox(
                        label="Download new Model",
                        info='Refer to "https://ollama.com/library" for all available models',
                        placeholder="gemma2:2b",
                        max_lines=1,
                        elem_id="mdl-name",
                    )
                with gr.Row():
                    unload_btn = gr.Button("Unload Current Model to Free Memory")
                    pull_btn = gr.Button("Download")

            with gr.Accordion("Configs", open=True):
                with gr.Row():
                    config_default_model = gr.Dropdown(
                        label="Default Model",
                        choices=all_models,
                        value=default_model,
                    )
                    config_default_tab = gr.Radio(
                        label="Default Tab",
                        choices=(
                            ("Options", "opt"),
                            ("Chat", "chat"),
                        ),
                        value=default_tab,
                    )
                    config_keep_alive = gr.Textbox(
                        label="Keep Alive Duration",
                        placeholder="5m",
                        max_lines=1,
                        value=keep_alive,
                        elem_id="mdl-name",
                    )
                    config_history_depth = gr.Slider(
                        label="History Depth",
                        value=history_depth,
                        minimum=0,
                        maximum=32,
                        step=2,
                    )

                save_config_btn = gr.Button("Save Configs")

            with gr.Accordion("Chat History", open=True):
                history_path = gr.Dropdown(
                    label="Filename to Save",
                    info="Will be saved to the log folder",
                    allow_custom_value=True,
                    multiselect=False,
                    choices=list_history(),
                    value=None,
                )

                with gr.Row():
                    save_history_btn = gr.Button("Save History")
                    load_history_btn = gr.Button("Load History")

        with gr.Tab(label="Chat", id="chat"):
            bot = gr.Chatbot(value=[], type="messages")
            gr.ChatInterface(
                fn=chat,
                type="messages",
                chatbot=bot,
                multimodal=True,
                additional_inputs=[model],
                analytics_enabled=False,
            )

    unload_btn.click(fn=unload_model)
    pull_btn.click(fn=pull_model, inputs=[mdl_name]).success(
        fn=lambda: [
            gr.update(choices=list_models()),
            gr.update(choices=list_models()),
        ],
        outputs=[model, config_default_model],
    )

    save_config_btn.click(
        fn=save_configs,
        inputs=[
            config_default_model,
            config_default_tab,
            config_keep_alive,
            config_history_depth,
        ],
    )

    save_history_btn.click(
        fn=save_history,
        inputs=[history_path, bot],
    ).success(fn=lambda: gr.update(choices=list_history()), outputs=[history_path])
    load_history_btn.click(fn=load_history, inputs=[history_path], outputs=[bot])

    block.load(fn=None, js=JS)
    block.unload(fn=unload_model)

demo = block

if __name__ == "__main__":
    demo.launch()
