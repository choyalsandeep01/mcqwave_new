import asyncio
from pyppeteer import launch

async def generate_pdf(url, output_path="output.pdf"):
    """
    Generates a PDF of a webpage with scroll-triggered animations by simulating
    scrolling behavior and forcing visibility of all elements, while removing unwanted script content.
    """
    
    chrome_path = r"C:\Program Files\Google\Chrome\Application\chrome.exe"
    
    browser = await launch(
        headless=True,
        executablePath=chrome_path,
        args=[
            "--no-sandbox",
            "--disable-setuid-sandbox",
            "--disable-dev-shm-usage",
            "--disable-accelerated-2d-canvas",
            "--disable-gpu",
            "--start-maximized"
        ]
    )
    
    page = await browser.newPage()
    await page.setViewport({"width": 1349, "height": 1080, "deviceScaleFactor": 1})
    
    # Inject JavaScript to override scroll-based visibility
    await page.evaluateOnNewDocument('''() => {
        // Previous intersection observer and scroll override code remains the same
        const observerCallback = function() {};
        window.IntersectionObserver = function() {
            return {
                observe: function() {},
                unobserve: function() {},
                disconnect: function() {}
            };
        };
        
        Object.defineProperty(window, 'scrollY', { get: () => 999999 });
        Object.defineProperty(window, 'pageYOffset', { get: () => 999999 });
        Object.defineProperty(document.documentElement, 'scrollTop', { get: () => 999999 });
        
        Object.defineProperty(HTMLElement.prototype, 'getBoundingClientRect', {
            get: function() {
                return function() {
                    return {
                        top: 0,
                        left: 0,
                        bottom: 100,
                        right: 100,
                        width: 100,
                        height: 100,
                        x: 0,
                        y: 0,
                        toJSON: () => {}
                    };
                };
            }
        });
    }''')
    
    print("🔄 Navigating to the page...")
    await page.goto(url, {
        "waitUntil": "networkidle0",
        "timeout": 60000
    })
    
    print("⚡ Handling animated elements and removing script content...")
    
    # Enhanced page cleanup and element visibility
    await page.evaluate('''() => {
        // Remove all script tags and their content
        const scripts = document.getElementsByTagName('script');
        while(scripts.length > 0) {
            scripts[0].parentNode.removeChild(scripts[0]);
        }
        
        // Remove inline JavaScript content that might be visible
        document.querySelectorAll('*').forEach(element => {
            // Remove onclick attributes and other JavaScript handlers
            const attrs = element.attributes;
            const removeAttrs = [];
            for(let i = 0; i < attrs.length; i++) {
                if(attrs[i].name.startsWith('on') || 
                   attrs[i].value.includes('javascript:')) {
                    removeAttrs.push(attrs[i].name);
                }
            }
            removeAttrs.forEach(attr => element.removeAttribute(attr));
            
            // Remove any text content that looks like JavaScript
            if(element.textContent && (
                element.textContent.includes('function') ||
                element.textContent.includes('addEventListener') ||
                element.textContent.includes('document.getElementById')
            )) {
                if(!element.children.length) {  // Only clear if no child elements
                    element.textContent = '';
                }
            }
        });
        
        function makeVisible(element) {
            const style = window.getComputedStyle(element);
            if (style.display === 'none') element.style.display = 'block';
            if (style.visibility === 'hidden') element.style.visibility = 'visible';
            if (style.opacity === '0') element.style.opacity = '1';
            
            element.style.transform = 'none';
            element.style.animation = 'none';
            element.style.transition = 'none';
            
            const animationClasses = [
                'invisible',
                'opacity-0',
                'translate-y-full',
                'translate-x-full',
                '-translate-y-full',
                '-translate-x-full',
                'scale-0',
                'rotate-180',
                'aos-animate',
                'animate__animated'
            ];
            
            element.classList.remove(...animationClasses);
            element.setAttribute('data-scroll-visible', 'true');
        }
        
        // Process all elements
        const allElements = document.getElementsByTagName('*');
        for (const element of allElements) {
            makeVisible(element);
        }
        
        // Trigger scroll events
        for (let i = 0; i < document.documentElement.scrollHeight; i += 100) {
            window.scrollTo(0, i);
        }
        window.scrollTo(0, 0);
        
        // Force all elements to be in viewport
        document.querySelectorAll('*').forEach(el => {
            if (el instanceof HTMLElement) {
                const rect = el.getBoundingClientRect();
                if (rect.top < 0 || rect.top > window.innerHeight) {
                    el.style.top = '0px';
                }
            }
        });
    }''')
    
    # Rest of the code remains the same
    print("📜 Simulating scroll...")
    height = await page.evaluate('document.documentElement.scrollHeight')
    viewport_height = await page.evaluate('window.innerHeight')
    for position in range(0, height, 100):
        await page.evaluate(f'window.scrollTo(0, {position})')
        await asyncio.sleep(0.1)
    
    await asyncio.sleep(2)
    
    print("⏳ Ensuring all content is loaded...")
    await page.evaluate('''() => {
        return new Promise(resolve => {
            const checkContent = () => {
                const elements = document.querySelectorAll('[data-scroll-visible]');
                if (elements.length > 0) {
                    resolve();
                } else {
                    setTimeout(checkContent, 500);
                }
            };
            checkContent();
        });
    }''')
    
    total_height = await page.evaluate("Math.max(document.body.scrollHeight, document.documentElement.scrollHeight)")
    print(f"📏 Page Height Detected: {total_height}px")
    
    print("🖨 Generating PDF...")
    pdf_options = {
        "path": output_path,
        "printBackground": True,
        "width": "1349px",
        "height": f"{total_height}px",
        "scale": 1.0,
        "margin": {
            "top": "0px",
            "right": "0px",
            "bottom": "0px",
            "left": "0px"
        }
    }
    
    await page.pdf(pdf_options)
    await browser.close()
    print(f"✅ PDF saved successfully: {output_path}")

# Run the script
url = "https://mcqwave.com/"
asyncio.run(generate_pdf(url, "mcqwave_fullpage.pdf"))