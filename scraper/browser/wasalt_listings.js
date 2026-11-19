// Collects a random sample of Wasalt listings.
// How to run: open any page on https://wasalt.sa in a normal browser, open DevTools > Console,
// paste this file and press Enter. It saves wasalt_listings.json when it finishes (about 10 minutes).

const SITEMAP_URL = "https://cdn.wasalt.sa/sitemap/product_sitemap_en_sa.xml.gz";
const SALE_COUNT = 240;
const RENT_COUNT = 110;
const DELAY_MS = 1200;

// small seeded random generator so the same sample is picked every time
function makeRandom(seed) {
  return function () {
    seed = (seed * 1664525 + 1013904223) % 4294967296;
    return seed / 4294967296;
  };
}

function shuffle(list, random) {
  const copy = [...list];
  for (let i = copy.length - 1; i > 0; i--) {
    const j = Math.floor(random() * (i + 1));
    const temp = copy[i];
    copy[i] = copy[j];
    copy[j] = temp;
  }
  return copy;
}

function stripHtml(html) {
  return (html || "").replace(/<[^>]+>/g, " ").replace(/&nbsp;/g, " ").replace(/\s+/g, " ").trim();
}

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

function parseListing(url, html) {
  // listing pages are Next.js pages: the data is in __NEXT_DATA__ plus schema.org JSON-LD
  const nextData = html.match(/<script id="__NEXT_DATA__"[^>]*>([\s\S]*?)<\/script>/);
  const property = JSON.parse(nextData[1]).props.pageProps.propertyDetailsV3;

  let offer = {};
  const jsonLdBlocks = html.matchAll(/<script type="application\/ld\+json"[^>]*>([\s\S]*?)<\/script>/g);
  for (const block of jsonLdBlocks) {
    try {
      const item = JSON.parse(block[1]);
      if (item.offers) offer = item;
    } catch (e) {}
  }

  const info = property.propertyInfo || {};
  const breadcrumbs = info.breadCrumbs || [];
  const attrs = {};
  for (const attr of (property.attributes || []).concat(property.additionalAttributes || [])) {
    if (attr && attr.key) attrs[attr.key] = attr.value;
  }

  // only the agency name is kept, no agent names or phone numbers
  const owner = property.propertyOwner || {};

  return {
    id: property.id,
    url: url,
    purpose: url.includes("/rent/") ? "rent" : "sale",
    title: offer.name || null,
    price: offer.offers && offer.offers[0] ? offer.offers[0].price : null,
    currency: info.currencyType || "SAR",
    main_type: info.propertyMainType,
    category: breadcrumbs[0] ? breadcrumbs[0].title : null,
    city: breadcrumbs[1] ? breadcrumbs[1].subtitle : null,
    zone: breadcrumbs[2] ? breadcrumbs[2].subtitle : null,
    district: breadcrumbs[3] ? breadcrumbs[3].subtitle : null,
    address: info.address,
    lat: (property.location || {}).lat,
    lon: (property.location || {}).lon,
    attrs: attrs,
    description: stripHtml(offer.description).slice(0, 600),
    company: owner.enCmpName || owner.arCmpName || null,
    rega_licensed: !!property.isRegaProp,
    verified: !!property.isVerified,
    published: property.publishedAt,
    updated: property.updatedAt,
    image: offer.image || null
  };
}

async function collectListings() {
  const sitemap = await (await fetch(SITEMAP_URL)).text();
  const allUrls = [...sitemap.matchAll(/<loc>([^<]+)<\/loc>/g)].map(match => match[1]);

  const random = makeRandom(42);
  const saleUrls = shuffle(allUrls.filter(url => url.includes("/property/sale/")), random).slice(0, SALE_COUNT);
  const rentUrls = shuffle(allUrls.filter(url => url.includes("/property/rent/")), random).slice(0, RENT_COUNT);
  const queue = saleUrls.concat(rentUrls);
  console.log(`Sitemap has ${allUrls.length} listings, collecting ${queue.length}`);

  const listings = [];
  const errors = [];

  for (const url of queue) {
    try {
      const response = await fetch(url);
      const html = await response.text();

      // stop straight away if the site starts showing a bot check
      if (response.status === 403 || html.includes("Just a moment")) {
        console.log("Bot check shown, stopping");
        break;
      }
      if (response.status !== 200) {
        errors.push([url, response.status]);  // usually 404 for removed listings
      } else {
        listings.push(parseListing(url, html));
      }
    } catch (e) {
      errors.push([url, String(e)]);
    }

    if (listings.length % 25 === 0) console.log(`${listings.length} collected`);
    await sleep(DELAY_MS);
  }

  console.log(`Done: ${listings.length} listings, ${errors.length} errors`);
  saveFile("wasalt_listings.json", listings);
}

collectListings();
