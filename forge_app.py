from typing import Generator
import gradio as gr
import subprocess
import ollama
import json

# ================ Launch the Ollama Server ================ #
subprocess.run(["ollama", "list"], stdout=subprocess.DEVNULL)
# ========================================================== #

with open("../script.js", "r", encoding="utf-8") as script:
    JS: str = script.read()

CONFIG: dict = None
CONFIG_PATH: str = "../config.json"
"""path to user settings"""

LAST_USED_MODEL: str = None
"""pass into keep_alive to unload"""


def list_models() -> list[str]:
    """List all locally available models"""
    models: list[dict] = ollama.list().get("models", [])
    return [model["name"] for model in models]


def pull_model(model: str):
    """Download selected model"""
    try:
        gr.Info(f'Downloading "{model}"...')
        ollama.pull(model)
        gr.Info(f'Model "{model}" is ready!')
    except ollama._types.ResponseError:
        raise gr.Error("Failed to download model...")


def unload():
    """Free the memory occupied by model"""
    if LAST_USED_MODEL is not None:
        ollama.generate(model=LAST_USED_MODEL, prompt="", keep_alive=0)


def chat(query: dict, history: list[tuple[str]], model: str) -> str:
    if model is None or not model.strip():
        raise gr.Error("No Model Selected...")

    multi_modal = True
    files: list[dict] = query.get("files", [])
    query: str = query.get("text", "")
    if not files:
        multi_modal = False

    if not multi_modal and not query.strip():
        raise gr.Error("Inputs are Empty...")

    images: list[str] = []
    if multi_modal:
        if len(files) > 1:
            gr.Warning(
                """Multiple files is currently not supported...
                (using the first file in this message)"""
            )

        file = files[0]
        file_path: str = file["path"]
        file_type: str = file.get("mime_type", "")

        if "text" in file_type:
            with open(file_path, "r", encoding="utf-8") as f:
                data = f.read()
            query = f"{query}\n\n```\n{data}\n```"

        elif "image" in file_type:
            images.append(file_path)

        else:
            flag = False
            for T in ("json", "yaml", "xml"):
                if file_path.endswith(T):
                    with open(file_path, "r", encoding="utf-8") as f:
                        data = f.read()
                    query = f"{query}\n\n```{T}\n{data}\n```"
                    flag = True
                    break

            if not flag:
                if file_path.endswith("pdf"):
                    gr.Warning("PDF is currently not supported...")
                elif bool(file_type):
                    raise gr.Error(f'Unsupported File Type: "{file_type}"...')
                else:
                    raise gr.Error("Unrecognized File Type...")

    messages: list[dict] = []

    for msg in history:
        q, r = msg
        if q is None or isinstance(q, tuple) or not q.strip():
            continue
        if r is None or isinstance(r, tuple) or not r.strip():
            continue

        messages.append({"role": "user", "content": q})
        messages.append({"role": "assistant", "content": r})

    messages.append({"role": "user", "content": query})

    if images:
        messages[-1].update({"images": images})

    global LAST_USED_MODEL
    if LAST_USED_MODEL != model:
        unload()
        LAST_USED_MODEL = model

    response = ollama.chat(model=model, messages=messages, keep_alive="5m")
    return str(response["message"]["content"])


def chat_stream(
    query: str, history: list[tuple[str]], model: str
) -> Generator[str, None, None]:
    if model is None or not model.strip():
        raise gr.Error("No Model Selected...")

    if not query.strip():
        raise gr.Error("Message is Empty...")

    messages: list[dict] = []

    for msg in history:
        q, r = msg
        if q is None or not q.strip():
            continue
        if r is None or not r.strip():
            continue

        messages.append({"role": "user", "content": q})
        messages.append({"role": "assistant", "content": r})

    messages.append({"role": "user", "content": query})

    global LAST_USED_MODEL
    if LAST_USED_MODEL != model:
        unload()
        LAST_USED_MODEL = model

    response = ""
    for part in ollama.chat(model=model, messages=messages, stream=True):
        response += str(part["message"]["content"])
        yield response


def load_configs() -> tuple[list, str, str]:
    global CONFIG
    with open(CONFIG_PATH, "r", encoding="utf-8") as file:
        CONFIG = json.load(file)

    all_models: list[str] = list_models()

    mdl: str | None = CONFIG.get("default_model", None)
    default_model: str = (
        (mdl if mdl in all_models else all_models[0]) if all_models else None
    )

    default_tab: str = CONFIG.get("default_tab", "opt")

    return (all_models, default_model, default_tab)


def save_configs(mdl: str, tab: str):
    CONFIG["default_model"] = mdl
    CONFIG["default_tab"] = tab

    with open(CONFIG_PATH, "w", encoding="utf-8") as file:
        json.dump(CONFIG, file)

    gr.Info("Config Saved!")


with gr.Blocks(css="../style.css").queue() as block:
    all_models, default_model, default_tab = load_configs()

    with gr.Tabs(selected=default_tab):
        with gr.Tab(label="Options", id="opt"):
            with gr.Row(variant="panel"):
                with gr.Column(variant="compact"):
                    model = gr.Dropdown(
                        label="Model",
                        info="All locally available models",
                        value=default_model,
                        choices=all_models,
                    )
                    unload_btn = gr.Button("Unload Current Model to Free Memory")
                with gr.Column(variant="compact"):
                    mdl_name = gr.Textbox(
                        label="Download new Model",
                        info='Refer to "https://ollama.com/library" for all available models',
                        placeholder="gemma2:2b",
                        max_lines=1,
                        elem_id="mdl-name",
                    )
                    pull_btn = gr.Button("Download")

            with gr.Accordion("Configs", open=False):
                config_default_model = gr.Dropdown(
                    label="Default Model",
                    value=default_model,
                    choices=all_models,
                )
                config_default_tab = gr.Radio(
                    label="Default Tab",
                    choices=(
                        ("Options", "opt"),
                        ("Chat", "chat"),
                        ("Multi-Modal Chat", "chat-m"),
                    ),
                    value=default_tab,
                )

                save_btn = gr.Button("Save")

            unload_btn.click(fn=unload)
            pull_btn.click(fn=pull_model, inputs=[mdl_name]).success(
                fn=lambda: [
                    gr.update(choices=list_models()),
                    gr.update(choices=list_models()),
                ],
                outputs=[model, config_default_model],
            )
            save_btn.click(
                fn=save_configs,
                inputs=[config_default_model, config_default_tab],
            )

        with gr.Tab(label="Chat", id="chat"):
            gr.ChatInterface(
                fn=chat_stream,
                multimodal=False,
                additional_inputs=[model],
                analytics_enabled=False,
            )
        with gr.Tab(label="Multi-Modal Chat", id="chat-m"):
            gr.ChatInterface(
                fn=chat,
                multimodal=True,
                additional_inputs=[model],
                analytics_enabled=False,
            )

    block.load(fn=None, js=JS)
    block.unload(fn=unload)

demo = block

if __name__ == "__main__":
    demo.launch()
