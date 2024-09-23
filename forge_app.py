from typing import Generator
import gradio as gr
import subprocess
import ollama
import spaces

# ================ Launch the Ollama Server ================ #
subprocess.run(["ollama", "list"], stdout=subprocess.DEVNULL)
# ========================================================== #


LAST_USED_MODEL: str = None
"""pass into keep_alive to unload"""


def list_models() -> list[str]:
    """List all locally available models"""

    models: list[dict] = ollama.list().get("models", [])
    mdl = [model["name"] for model in models]

    return mdl


def pull_model(model: str):
    """Download selected model"""

    gr.Info(f'Downloading "{model}"...')

    try:
        ollama.pull(model)
    except ollama._types.ResponseError:
        raise gr.Error("Failed to download model...")

    gr.Info(f'Model "{model}" is ready!')


def unload():
    """Free the memory occupied by model"""
    if LAST_USED_MODEL is not None:
        ollama.generate(model=LAST_USED_MODEL, prompt="", keep_alive=0)


def chat(query: dict, history: list[tuple[str]], model: str) -> str:
    global LAST_USED_MODEL

    if model is None or not model.strip():
        raise gr.Error("No Model Selected...")

    multi_modal = True
    files: list[dict] = query.get("files", [])
    query: str = query.get("text", "")
    if not files:
        multi_modal = False

    assert isinstance(query, str)
    if not multi_modal and not query.strip():
        raise gr.Error("Empty Inputs...")

    if multi_modal:
        if len(files) > 1:
            gr.Warning("Only 1 file is supported at a time...")

        img = None
        file: dict = files[0]

        file_path: str = file["path"]
        file_type: str = file.get("mime_type", "")

        if "text" in file_type:
            with open(file_path, "r", encoding="utf-8") as f:
                data = f.read()
            query = f"{query}\n{data}"

        elif "image" in file_type:
            img: str = file_path

        else:
            flag = False
            for T in ("json", "yaml", "xml"):
                if file_path.endswith(T):
                    with open(file_path, "r", encoding="utf-8") as f:
                        data = f.read()
                    query = f"{query}\n```{T}\n{data}\n```"
                    flag = True
                    break

            if not flag:
                if file_path.endswith("pdf"):
                    raise gr.Error("PDF files are not supported...")
                elif not file_type:
                    raise gr.Error("Unrecognized File Type...")
                else:
                    raise gr.Error(f"Unsupported File Type: [{file_type}]...")

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
    if multi_modal and img:
        messages[-1].update({"images": [img]})

    if LAST_USED_MODEL != model:
        unload()
        LAST_USED_MODEL = model

    response = ollama.chat(model=model, messages=messages, keep_alive="5m")
    return str(response["message"]["content"])


def chat_stream(
    query: str, history: list[tuple[str]], model: str
) -> Generator[str, None, None]:
    global LAST_USED_MODEL

    if model is None or not model.strip():
        raise gr.Error("No Model Selected...")

    assert isinstance(query, str)
    if not query.strip():
        raise gr.Error("Empty Prompt Input...")

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

    if LAST_USED_MODEL != model:
        unload()
        LAST_USED_MODEL = model

    response = ""
    for part in ollama.chat(model=model, messages=messages, stream=True):
        response += str(part["message"]["content"])
        yield response


with open("../script.js", "r", encoding="utf-8") as script:
    JS = script.read()

block = gr.Blocks(css="../style.css").queue()
with block:

    mdl = list_models()
    no_mdl: bool = len(mdl) == 0

    with gr.Tabs(selected="mdl" if no_mdl else "chat"):

        with gr.Tab(label="Models", id="mdl"):

            with gr.Row(variant="panel"):

                with gr.Column(variant="compact"):
                    model = gr.Dropdown(
                        label="Model",
                        info="All local models",
                        value=None if no_mdl else mdl[0],
                        choices=mdl,
                        allow_custom_value=False,
                        multiselect=False,
                    )

                    unload_btn = gr.Button("Unload Current Model to Free Memory")

                with gr.Column(variant="compact"):
                    mdl_name = gr.Textbox(
                        label="Model to Download",
                        info='Refer to "https://ollama.com/library" for all available models',
                        value="gemma2:2b",
                        placeholder="gemma2:2b",
                        lines=1,
                        max_lines=1,
                        interactive=True,
                        elem_id="mdl-name",
                    )

                    pull_btn = gr.Button("Download")

            mm_cb = gr.Checkbox(
                value=False,
                label="Multi-Modal",
                info="Enable uploading images and text files",
            )

            unload_btn.click(fn=unload)

            pull_btn.click(fn=pull_model, inputs=[mdl_name]).success(
                fn=lambda: gr.update(choices=list_models()),
                inputs=None,
                outputs=[model],
            )

        with gr.Tab(label="Chat", id="chat", visible=True) as tab_chat:
            gr.ChatInterface(
                fn=chat_stream,
                multimodal=False,
                fill_height=True,
                fill_width=True,
                additional_inputs=[model],
                analytics_enabled=False,
            )

        with gr.Tab(label="Multi-Modal Chat", id="chat-m", visible=False) as tab_chat_m:
            gr.ChatInterface(
                fn=chat,
                multimodal=True,
                fill_height=True,
                fill_width=True,
                additional_inputs=[model],
                analytics_enabled=False,
            )

        def on_mode(cb: bool):
            return [gr.update(visible=(not cb)), gr.update(visible=cb)]

        mm_cb.change(fn=on_mode, inputs=[mm_cb], outputs=[tab_chat, tab_chat_m])

    block.load(fn=None, js=JS)
    block.unload(fn=unload)

demo = block

if __name__ == "__main__":
    demo.launch()
