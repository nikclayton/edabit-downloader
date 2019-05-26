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
                results.source_url = request.url;
                results.challenge_id = request.url.substring(29);

                results.author_id = await page.$eval('a[href*=user]', el => el.innerText);
                results.author_url = await page.$eval('a[href*=user]', el => el.href);

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
                results.code = await page.$$eval('#Code div.CodeMirror-code pre', els =>
                    els.map(el => el.innerText).join('\n'));

                // Find the tests. Show them by clicking on the 6th tab.
                await page.$$eval('div[role=tab]', els => els[5].click());
                results.tests = await page.$eval('#Lab textarea', el => el.innerText);

                console.log(results);
                Apify.pushData(results);
                return;
            }

            const pageFunction = ($divs) => {
                const reqs = [];
                $divs.forEach(($div) => {
                    const a = $div.querySelector('a.content');
                    const difficulty = $div.querySelector('div.difficulty').innerText;

                    reqs.push({
                        url: a.href,
                        userData: {
                            original_url: a.href,
                            label: 'CHALLENGE',
                            difficulty: difficulty,
                        }
                    })
                });

                return reqs;
            };

            let reqs;
            console.log('Loading the list of challenges');
            try {
                let i = 0;
                while (await page.waitForSelector('button.ui.fluid.button', {timeout: 5000})) {
                    await page.$eval('button.ui.fluid.button', el => el.click());
                }
            } catch (error) {
                console.log('Timed out waiting for button, assuming all content is loaded.')
            }
            console.log('Collecting requests...');
            reqs = await page.$$eval('#Main div[role=listitem]', pageFunction);
            console.log(reqs);

            reqs.forEach(req => {
                requestQueue.addRequest(new Apify.Request(req));
            });
        },
        maxRequestsPerCrawl: 500,
        maxConcurrency: 10,
    });

    await crawler.run();
});
