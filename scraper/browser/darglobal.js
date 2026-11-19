// Collects Dar Global projects (structured) and the text of project, partner, about, FAQ and press pages.
// How to run: open https://darglobal.co.uk in a normal browser, open DevTools > Console, paste and press Enter.
// It saves darglobal_projects.json and darglobal_pages.json (about 3 minutes).

const BASE = "https://darglobal.co.uk";
const DELAY_MS = 1500;

const EXTRA_PAGES = [
  "/", "/about", "/why-invest", "/faq", "/hospitality", "/luxury-golf-communities",
  "/exclusive-membership", "/commercial", "/tokenization", "/one-of-one", "/investor",
  "/partners/pagani", "/partners/the-trump-organization", "/partners/w-hotels", "/partners/paramount",
  "/partners/aston-martin", "/partners/elie-saab", "/partners/fendi-casa", "/partners/lamborghini",
  "/partners/marriott-residences-aida-oman", "/partners/missoni", "/partners/mouawad",
  "/projects/properties-in-uae", "/projects/properties-in-uk", "/projects/properties-in-saudi-arabia",
  "/projects/properties-in-oman", "/projects/properties-in-qatar", "/projects/properties-in-spain"
];

function sleep(ms) {
  return new Promise(resolve => setTimeout(resolve, ms));
}

function stripHtml(html) {
  return String(html || "").replace(/<[^>]+>/g, " ").replace(/&nbsp;/g, " ").replace(/\s+/g, " ").trim();
}

function saveFile(name, data) {
  const blob = new Blob([JSON.stringify(data)], { type: "application/json" });
  const link = document.createElement("a");
  link.href = URL.createObjectURL(blob);
  link.download = name;
  link.click();
}

function readNextData(html) {
  const match = html.match(/<script id="__NEXT_DATA__"[^>]*>([\s\S]*?)<\/script>/);
  if (!match) return null;
  return JSON.parse(match[1]).props.pageProps;
}

// the /projects page has one tab per country, each with project cards
function readProjects(pageProps) {
  const projects = {};

  for (const tab of pageProps.pageData.attributes.Tabs) {
    for (const card of tab.TabData || []) {
      const name = card.ProjectTitle;
      if (projects[name]) continue;

      let link = card.Link && (card.Link.href || card.Link.url || card.Link);
      if (typeof link === "string" && link.startsWith("/")) link = BASE + link;

      projects[name] = {
        name: name,
        description: stripHtml(card.ProjectDescription).slice(0, 600),
        location: stripHtml(card.Location),
        country: tab.TabHeading,
        bedrooms: stripHtml(card.Bedrooms),
        project_type: stripHtml(card.ProjectType),
        completion: stripHtml(card.completionDate),
        url: link
      };
    }
  }
  return Object.values(projects);
}

// some pages render on the client, so their text is only inside __NEXT_DATA__
function textFromNextData(pageProps) {
  delete pageProps.globalData;
  const pieces = [];
  const seen = new Set();

  function walk(value, key) {
    if (typeof value === "string") {
      const isAsset = /^https?:|\.(webp|jpg|png|svg|mp4)$|^[\w-]+$/.test(value);
      const isMetaKey = /^(seo|meta|og|url|href|link|slug|image)/i.test(key || "");
      const text = stripHtml(value);
      if (value.length > 25 && !isAsset && !isMetaKey && text.length > 25 && !seen.has(text)) {
        seen.add(text);
        pieces.push(text);
      }
    } else if (Array.isArray(value)) {
      for (const item of value) walk(item, key);
    } else if (value && typeof value === "object") {
      for (const childKey in value) walk(value[childKey], childKey);
    }
  }

  walk(pageProps, "");
  return pieces.join(" . ");
}

function pageText(html) {
  const doc = new DOMParser().parseFromString(html, "text/html");
  for (const element of doc.querySelectorAll("script, style, noscript, svg, header, footer, nav, form")) {
    element.remove();
  }
  return { title: (doc.title || "").trim(), text: (doc.body.textContent || "").replace(/\s+/g, " ").trim() };
}

async function collectDarGlobal() {
  const projectsHtml = await (await fetch(BASE + "/projects")).text();
  const projects = readProjects(readNextData(projectsHtml));
  console.log(`Found ${projects.length} projects`);

  const urls = new Set();
  for (const project of projects) {
    if (project.url && project.url.startsWith(BASE)) urls.add(project.url);
  }
  for (const path of EXTRA_PAGES) urls.add(BASE + path);

  const pages = [];
  for (const url of urls) {
    try {
      const response = await fetch(url);
      const html = await response.text();
      if (response.status !== 200) {
        console.log("Skipped", url, response.status);
        continue;
      }

      const page = pageText(html);
      if (page.text.length < 400) {
        const pageProps = readNextData(html);
        if (pageProps) page.text = (page.text + " " + textFromNextData(pageProps)).trim();
      }
      if (page.text.length > 100) {
        pages.push({ url: url, title: page.title, text: page.text.slice(0, 15000) });
      }
    } catch (e) {
      console.log("Failed", url, e);
    }
    await sleep(DELAY_MS);
  }

  console.log(`Done: ${pages.length} pages`);
  saveFile("darglobal_projects.json", projects);
  saveFile("darglobal_pages.json", pages);
}

collectDarGlobal();
