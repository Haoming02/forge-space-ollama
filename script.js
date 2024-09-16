function init() {
    const textbox = document.getElementById("mdl-name");
    const info = textbox.querySelector("label").querySelector("div");
    info.innerHTML = 'Refer to the <a class="link" href="https://ollama.com/library">Library</a> for all available models';
}
