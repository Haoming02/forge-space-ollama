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
        ollama.generate(model=LAST_USED_MODEL, prompt="", keep_alive="0m")


def chat(query: str, history: list[tuple[str]], model: str) -> str:
    global LAST_USED_MODEL

    if model is None or not model.strip():
        raise gr.Error("No Model Selected...")

    if not query.strip():
        gr.Warning("Empty Input...")
        return None

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

    response = ollama.chat(model=model, messages=messages, keep_alive="5m")
    LAST_USED_MODEL = model
    return response["message"]["content"]


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

            unload_btn.click(fn=unload)

            pull_btn.click(fn=pull_model, inputs=[mdl_name]).success(
                fn=lambda: gr.update(choices=list_models()),
                inputs=None,
                outputs=[model],
            )

        with gr.Tab(label="Chat", id="chat"):
            gr.ChatInterface(
                fn=chat, fill_height=True, fill_width=True, additional_inputs=[model]
            )

    block.load(fn=None, js=JS)
    block.unload(fn=unload)

demo = block

if __name__ == "__main__":
    demo.launch()
