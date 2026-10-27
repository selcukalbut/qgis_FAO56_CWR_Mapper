// Runs the Sulama Programlama web app's own code headless (puppeteer-core + Chrome) and
// writes its daily rows and totals to JSON. Usage (from the web app folder, which has puppeteer-core):
//   NODE_PATH=$PWD/node_modules node run_web_app.js /abs/path/sulama-ders.html out.json '[cases]'
const puppeteer = require('puppeteer-core');
const fs = require('fs');
const [,, appHtml, outJson, casesJson] = process.argv;
const cases = JSON.parse(casesJson);
(async () => {
  const b = await puppeteer.launch({ executablePath: '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome', headless: 'new', args: ['--no-sandbox'] });
  const p = await b.newPage();
  await p.goto('file://' + appHtml, { waitUntil: 'networkidle2', timeout: 60000 });
  await new Promise(r => setTimeout(r, 1500));
  const out = {};
  for (const c of cases) {
    out[c.name] = await p.evaluate(async (c) => {
      document.getElementById('sulamaLat').value = String(c.lat);
      document.getElementById('sulamaLon').value = String(c.lon);
      document.getElementById('sulamaCrop').value = c.crop;
      document.getElementById('sulamaCrop').dispatchEvent(new Event('change', { bubbles: true }));
      document.getElementById('sulamaPlantDate').value = c.plant;
      sulamaSetRangeMode('manual');
      document.getElementById('sulamaStart').value = c.start;
      document.getElementById('sulamaEnd').value = c.end;
      document.getElementById('sulamaEffRain').checked = true;
      await sulamaCalculate();
      const r = sulamaLastResult;
      const crop = SULAMA_CROPS.find(x => x.id === c.crop);
      return r ? { crop, sumEto: r.sumEto, sumEtc: r.sumEtc, sumRain: r.sumRain, effRain: r.effRain, netReq: r.netReq,
                   rows: r.rows.map(x => ({ date: x.date, eto: x.eto, kc: x.kc, etc: x.etc, rain: x.rain, rh: x.rh })) } : null;
    }, c);
  }
  fs.writeFileSync(outJson, JSON.stringify(out));
  await b.close();
})();
