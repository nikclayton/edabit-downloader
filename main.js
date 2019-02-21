const Apify = require('apify');

const urlEdabit = 'https://edabit.com/challenges';
const urlChallenges = 'https://edabit.com/challenge/[.*]';

Apify.main(async () => {
    const requestQueue = await Apify.openRequestQueue();
    await requestQueue.addRequest(new Apify.Request({url: urlEdabit}));
    const pseudoUrls = [new Apify.PseudoUrl(urlChallenges)];

    const crawler = new Apify.PuppeteerCrawler({
        requestQueue,
        handlePageFunction: async ({request, page}) => {
            const title = await page.title();
            console.log(`Title of ${request.url}: ${title}`);

            if (request.userData.label === 'CHALLENGE') {
                console.log('Challenge page');
                await page.waitForSelector('h2.content', {timeout: 0});

                const results = {};
                results.difficulty = request.userData.difficulty;

                results.title = await page.$eval('h2.content', el => el.innerText);
                // Tags are a.ui.label, and there may be several of them.
                results.tags = await page.$$eval('a.ui.label', els => els.map(el => el.innerText));

                // Instructions are in 'div.instructions div' (no class)
                results.instructions = await page.$eval('div.instructions div:not([class])',
                    el => el.innerHTML);

                // Find sample code. First click the 'Code' tab.
                await page.$eval('div[role=tab]:nth-child(3)', el => el.click());
                // Code is in multiple <pre> elements in div.CodeMirror-code. Collect
                // them all and put new lines between them.
                results.code = await page.$$eval('div#Code div.CodeMirror-code pre', els =>
                    els.map(el => el.innerText).join('\n'));

                // Find the tests. Show them by clicking on the 6th tab.
                await page.$$eval('div[role=tab]', els => els[5].click());
                results.tests = await page.$$eval('div#Lab div.CodeMirror-code pre', els =>
                    els.map(el => el.innerText).join('\n'));

                console.log(results);
                Apify.pushData(results);
                return;
            }

            console.log('Waiting for button');
            await page.waitForSelector(/*'div.ui.container button'*/'a.content', {timeout: 0})
                .then(() => console.log('Button appeared'));
            console.log(`Match: ${pseudoUrls[0].matches('https://edabit.com/challenge/ARr5tA458o2tC9FTN')}`)
            const links = await Apify.utils.enqueueLinks({
                page,
                requestQueue,
                selector: 'a.content',
                pseudoUrls: pseudoUrls,
                userData: {
                    label: 'CHALLENGE',
                    difficulty: await page.$eval('div.difficulty', el => el.innerText)
                }
            });
        },
        maxRequestsPerCrawl: 50,
        maxConcurrency: 10,
    });

    await crawler.run();
});

