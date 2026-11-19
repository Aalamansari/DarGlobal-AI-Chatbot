// Collects the text of a few Wasalt info pages (home with FAQ, corporate).
// How to run: open https://wasalt.sa in a normal browser, open DevTools > Console, paste and press Enter.

const PAGES = [
  "https://wasalt.sa/en",
  "https://wasalt.sa/en/corporate"
];

function sleep(ms) {
  return new Promise(resolve => setTimeout(resolve, ms));
}

function saveFile(name, data) {
  const blob = new Blob([JSON.stringify(data)], { type: "application/json" });
  const link = document.createElement("a");
  link.href = URL.createObjectURL(blob);
  link.download = name;
  link.click();
}

async function collectPages() {
  const pages = [];

  for (const url of PAGES) {
    const html = await (await fetch(url)).text();
    const doc = new DOMParser().parseFromString(html, "text/html");
    for (const element of doc.querySelectorAll("script, style, noscript, svg, nav, footer")) {
      element.remove();
    }
    const main = doc.querySelector("main") || doc.body;
    const text = (main.innerText || main.textContent).replace(/\s+/g, " ").trim();

    pages.push({ url: url, title: doc.title, text: text.slice(0, 12000) });
    await sleep(1500);
  }

  saveFile("wasalt_pages.json", pages);
}

collectPages();
