#!/usr/bin/env python3
"""
Web scraper for kilointernational.com
Scrapes product data and images with intelligent folder merging.
"""

import argparse
import json
import os
import re
import sys
from pathlib import Path
from urllib.parse import urljoin, urlparse
import requests
from bs4 import BeautifulSoup
import markdownify as md


class KiloWebScraper:
    """Web scraper for Kilo International website"""
    
    # Define all subdirectories to create
    SUBDIRS = [
        'block_diagrams',
        'design_resources',
        'documentation',
        'images',
        'markdowns',
        'other',
        'software_tools',
        'tables',
        'trainings'
    ]
    
    def __init__(self, url, output_dir):
        self.url = url
        self.output_dir = Path(output_dir)
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        })
        
    def fetch_page(self, url):
        """Fetch page content"""
        try:
            response = self.session.get(url, timeout=30)
            response.raise_for_status()
            return response.text
        except requests.RequestException as e:
            print(f"Error fetching {url}: {e}")
            return None
    
    def create_folder_structure(self):
        """Create all subdirectories and their specific json files"""
        print("Creating folder structure...")
        
        # Check if the output directory is 'category'
        output_dir_name = self.output_dir.name
        
        # For 'category', only create markdowns and tables
        if output_dir_name == 'category':
            subdirs_to_create = ['markdowns', 'tables']
        else:
            # For other directories (part, part1, etc.), create all subdirectories
            subdirs_to_create = self.SUBDIRS
        
        # files to create in each directory
        dir_files = {
            'block_diagrams': ['block_diagram_mappings.json'],
            'design_resources': ['metadata.json'],
            'documentation': ['metadata.json'],
            'images': ['metadata.json'],
            'markdowns': [], # No json file observed in find_by_name
            'other': ['metadata.json'],
            'software_tools': ['metadata.json'],
            'tables': ['metadata.json', 'products.json'],
            'trainings': ['metadata.json']
        }
        
        for subdir in subdirs_to_create:
            subdir_path = self.output_dir / subdir
            subdir_path.mkdir(parents=True, exist_ok=True)
            
            if subdir in dir_files:
                for filename in dir_files[subdir]:
                    file_path = subdir_path / filename
                    if not file_path.exists():
                        initial_content = {} if filename == 'products.json' else []
                        with open(file_path, 'w', encoding='utf-8') as f:
                            json.dump(initial_content, f)
    
    def is_logo_image(self, url):
        if not url:
            return False
        url_lower = url.lower()
        if 'logo' in url_lower or '_logo_' in url_lower or 'logo-' in url_lower or '-logo' in url_lower:
            return True
        filename = os.path.basename(urlparse(url).path).lower()
        return 'logo' in filename
    
    def detect_page_type(self, soup):
        product_list = soup.find(class_='productList')
        if product_list:
            return 'category'
        
        product_items = soup.find_all('a', class_='grid-item-link')
        
        if len(product_items) > 1:
            return 'category'
        else:
            return 'product_detail'
    
    def scrape_category_page(self, soup):
        products = {}
        images = []
        block_diagrams = []
        
        product_list = soup.find(class_='productList')
        if product_list:
            product_items = product_list.find_all('li', class_='grid-item')
        else:
            product_items = soup.find_all('li', class_='grid-item')
        
        print(f"Found {len(product_items)} product items in category page")
        
        for item in product_items:
            link_elem = item.find('a', class_='grid-item-link')
            if not link_elem:
                continue
            
            product_link = link_elem.get('href', '')
            if product_link:
                product_link = urljoin(self.url, product_link)
            
            title_elem = item.find('div', class_='grid-item-title')
            product_name = title_elem.get_text(strip=True) if title_elem else 'Unknown Product'
            
            # Extract product image using product-image class
            img_elem = item.find('img', class_='product-image')
            image_url = None
            if img_elem:
                image_url = img_elem.get('data-src') or img_elem.get('src')
                if image_url:
                    image_url = urljoin(self.url, image_url)
                    if not self.is_logo_image(image_url):
                        # Check extension to separate block diagrams (PNG) from product images
                        parsed = urlparse(image_url)
                        path = parsed.path.lower()
                        
                        if path.endswith('.png'):
                            block_diagrams.append(image_url)
                        else:
                            images.append(image_url)
            
            price_elem = item.find('div', class_='grid-item-price')
            price = price_elem.get_text(strip=True) if price_elem else None
            
            products[product_name] = {
                'Product': product_name,
                'description': None,
                'product_page_link': product_link,
                'image_url': image_url,
                'price': price,
                'pdf_link': None,
                'pdf_filename': None
            }
        
        return products, images, block_diagrams
    
    def extract_block_diagrams(self, soup):
        block_diagrams = []
        all_links = soup.find_all('a', href=True)
        
        for link in all_links:
            href = link.get('href', '')
            if 'static1.squarespace.com' in href or 'squarespace-cdn.com' in href:
                if '?format=' in href or href.endswith(('.png', '.jpg', '.jpeg', '.gif')):
                    full_url = urljoin(self.url, href)
                    if full_url not in block_diagrams:
                        block_diagrams.append(full_url)
        
        return block_diagrams
    
    def scrape_product_detail_page(self, soup):
        products = {}
        
        product_name = None
        h1_tag = soup.find('h1')
        if h1_tag:
            product_name = h1_tag.get_text(strip=True)
        
        description = None
        og_desc = soup.find('meta', property='og:description')
        if og_desc:
            description = og_desc.get('content')
        
        if not description:
            paragraphs = soup.find_all('p')
            desc_parts = []
            for p in paragraphs:
                text = p.get_text(strip=True)
                if text and len(text) > 20:
                    desc_parts.append(text)
            if desc_parts:
                description = ' '.join(desc_parts)
        
        image_url = None
        og_image = soup.find('meta', property='og:image')
        if og_image:
            image_url = og_image.get('content')
        
        specs = {}
        lists = soup.find_all('ul')
        for ul in lists:
            items = ul.find_all('li')
            for item in items:
                text = item.get_text(strip=True)
                if ':' in text:
                    key, value = text.split(':', 1)
                    specs[key.strip()] = value.strip()
        
        if product_name:
            products[product_name] = {
                'Product': product_name,
                'description': description,
                'product_page_link': self.url,
                'image_url': image_url,
                'specifications': specs if specs else None,
                'pdf_link': None,
                'pdf_filename': None
            }
        
        block_diagrams = self.extract_block_diagrams(soup)
        
        images = []
        all_images = soup.find_all('img')
        for img in all_images:
            img_url = img.get('data-src') or img.get('src')
            if img_url and ('squarespace-cdn.com' in img_url or 'static1.squarespace.com' in img_url):
                img_url = urljoin(self.url, img_url)
                
                # Check extension to separate block diagrams (PNG) from product images
                parsed = urlparse(img_url)
                path = parsed.path.lower()
                
                if path.endswith('.png'):
                    if img_url not in block_diagrams and not self.is_logo_image(img_url):
                        block_diagrams.append(img_url)
                else:
                    if img_url not in images and not self.is_logo_image(img_url):
                        images.append(img_url)
        
        return products, images, block_diagrams
    
    def download_file(self, url, save_dir):
        """Download file (image or other) and return filename"""
        try:
            response = self.session.get(url, timeout=30)
            response.raise_for_status()

            # Extract filename from URL
            parsed = urlparse(url)
            filename = os.path.basename(parsed.path.split('?')[0])  # Remove query parameters

            # If filename doesn't have extension, add one
            if not os.path.splitext(filename)[1]:
                content_type = response.headers.get('content-type', '')
                if 'jpeg' in content_type or 'jpg' in content_type:
                    filename += '.jpg'
                elif 'png' in content_type:
                    filename += '.png'
                elif 'gif' in content_type:
                    filename += '.gif'
                else:
                    filename += '.jpg'

            # If still no filename, generate one
            if not filename or filename == '.jpg':
                filename = f"image-{hash(url) % 10000}.jpg"

            # Handle filename conflicts
            filepath = save_dir / filename
            counter = 1
            base_name = os.path.splitext(filename)[0]
            ext = os.path.splitext(filename)[1]

            while filepath.exists():
                filename = f"{base_name}({counter}){ext}"
                filepath = save_dir / filename
                counter += 1

            # Save file
            with open(filepath, 'wb') as f:
                f.write(response.content)

            return filename

        except Exception as e:
            print(f"Error downloading file {url}: {e}")
            return None

    def load_existing_metadata(self, filepath):
        """Load existing metadata.json file"""
        if filepath.exists():
            try:
                with open(filepath, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except Exception as e:
                print(f"Error loading {filepath}: {e}")
                return []
        return []

    def load_existing_products(self, filepath):
        """Load existing products.json file"""
        if filepath.exists():
            try:
                with open(filepath, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except Exception as e:
                print(f"Error loading {filepath}: {e}")
                return {}
        return {}

    def save_json(self, data, filepath):
        """Save data to JSON file"""
        filepath.parent.mkdir(parents=True, exist_ok=True)
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=4, ensure_ascii=False)

    @staticmethod
    def _html_to_str(html):
        """Convert HTML to string"""
        if not html:
            return ""
        if isinstance(html, list):
            return " ".join(str(x) for x in html if x)
        if isinstance(html, (dict, int, float)):
            return str(html)
        return str(html)
    
    @staticmethod
    def clean_html_spaces(text: str) -> str:
        """Clean HTML spaces and normalize whitespace"""
        if not text:
            return ""
        return (
            text.replace("&nbsp;", " ")   # replace HTML non-breaking spaces
                .replace("\xa0", " ")     # replace unicode non-breaking spaces
                .replace("\u00a0", " ")   # extra safety
        )

    def write_overview_markdown(self, soup, div_selector, section_title=None, url=None):
        """Convert HTML section to markdown with enhanced processing"""
        div = soup.select_one(div_selector)
        if not div:
            div = soup
 
        parsed = urlparse(url)
        base_url = f"{parsed.scheme}://{parsed.netloc}"
 
        # Make relative URLs absolute
        for tag in div.select("a[href], img[src]"):
            if tag.name == "a" and tag.get("href", "").startswith("/"):
                tag["href"] = (base_url.rstrip("/") if base_url else "") + tag["href"]
            elif tag.name == "img" and tag.get("src", "").startswith("/"):
                tag["src"] = (base_url.rstrip("/") if base_url else "") + tag["src"]
        
        # Convert onclick buttons to links
        for btn in div.select("button[onclick]"):
            onclick = btn.get("onclick", "")
            m = re.search(r"location\.href\s*=\s*['\"]([^'\"]+)['\"]", onclick)
            if not m:
                continue
 
            href = m.group(1)
 
            # Make absolute if needed
            if href.startswith("/"):
                href = (base_url.rstrip("/") if base_url else "") + href
 
            # Create <a> tag
            a = soup.new_tag("a", href=href)
 
            # Preserve button text
            text = btn.get_text(strip=True)
            a.string = text if text else "Download"
 
            btn.replace_with(a)
 
        html_content = div.decode_contents().strip()
        if not html_content:
            return ""
 
        # Convert HTML → Markdown
        markdown_text = md.markdownify(html_content, heading_style="ATX")
 
        # Clean up and normalize whitespace
        markdown_text = self._html_to_str(markdown_text)
        markdown_text = self.clean_html_spaces(markdown_text)
 
        # 🔹 Remove excessive blank lines (3+ → 1)
        markdown_text = re.sub(r"\n{3,}", "\n\n", markdown_text.strip())
 
        # 🔹 Trim leading/trailing spaces per line
        markdown_text = "\n".join(line.strip() for line in markdown_text.splitlines())
 
        # Add section title if provided
        if section_title:
            section_header = f"## {section_title}\n\n"
        else:
            section_header = ""
 
        return section_header + markdown_text.strip() + "\n"

    def save_markdown(self, soup, page_type):
        """Convert HTML to markdown and save in markdowns folder"""
        markdowns_dir = self.output_dir / 'markdowns'

        # Determine filename and selector based on page type
        if page_type == 'category':
            filename = 'category_overview.md'
            selector = "#page-wrapper .container .main-content .info"
            section_title = "Category"
        else:
            filename = 'product_details.md'
            selector = "#page-wrapper .container .main-content"
            section_title = "Product Details"

        # Generate markdown content using the enhanced method
        markdown_content = self.write_overview_markdown(soup, selector, section_title, self.url)

        filepath = markdowns_dir / filename

        # Save markdown file
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(markdown_content)

        print(f"Saved markdown to: {filepath}")

    def scrape(self):
        """Main scraping method"""
        print(f"Fetching URL: {self.url}")

        # Create folder structure first
        self.create_folder_structure()

        html = self.fetch_page(self.url)

        if not html:
            print("Failed to fetch page")
            return False

        soup = BeautifulSoup(html, 'html.parser')
        page_type = self.detect_page_type(soup)

        print(f"Detected page type: {page_type}")

        # Scrape based on page type
        block_diagrams = []
        if page_type == 'category':
            products, images, block_diagrams = self.scrape_category_page(soup)
        else:
            products, images, block_diagrams = self.scrape_product_detail_page(soup)

        print(f"Found {len(products)} products")
        print(f"Found {len(images)} images")
        print(f"Found {len(block_diagrams)} block diagrams")

        # Define directories
        images_dir = self.output_dir / 'images'
        tables_dir = self.output_dir / 'tables'
        block_diagrams_dir = self.output_dir / 'block_diagrams'

        # Load existing data
        images_metadata_file = images_dir / 'metadata.json'
        products_file = tables_dir / 'products.json'
        block_diagrams_metadata_file = block_diagrams_dir / 'metadata.json'
        block_diagrams_mappings_file = block_diagrams_dir / 'block_diagram_mappings.json'

        existing_images_metadata = self.load_existing_metadata(images_metadata_file)
        existing_products = self.load_existing_products(products_file)
        existing_block_diagrams_metadata = self.load_existing_metadata(block_diagrams_mappings_file)

        # Track existing URLs to avoid duplicates
        existing_image_urls = {item['url'] for item in existing_images_metadata}
        existing_block_diagram_urls = {item['url'] for item in existing_block_diagrams_metadata}

        # Download and track new images
        new_image_metadata = []
        for img_url in images:
            if img_url in existing_image_urls:
                print(f"Skipping existing image: {img_url}")
                continue

            print(f"Downloading image: {img_url}")
            filename = self.download_file(img_url, images_dir)

            if filename:
                new_image_metadata.append({
                    'name': filename,
                    'url': img_url,
                    'file_path': f"{self.output_dir}/images/{filename}",
                    'version': None,
                    'date': None,
                    'language': None,
                    'description': None
                })

        # Download and track block diagrams
        new_block_diagram_metadata = []
        for bd_url in block_diagrams:
            if bd_url in existing_block_diagram_urls:
                print(f"Skipping existing block diagram: {bd_url}")
                continue

            print(f"Downloading block diagram: {bd_url}")
            filename = self.download_file(bd_url, block_diagrams_dir)

            if filename:
                new_block_diagram_metadata.append({
                    'name': filename,
                    'url': bd_url,
                    'file_path': f"{self.output_dir}/block_diagrams/{filename}",
                    'version': None,
                    'date': None,
                    'language': None,
                    'description': None
                })

        # Merge and save image metadata
        all_images_metadata = existing_images_metadata + new_image_metadata
        self.save_json(all_images_metadata, images_metadata_file)
        print(f"Saved {len(all_images_metadata)} total images to metadata")

        # Merge and save block diagram metadata
        all_block_diagrams_metadata = existing_block_diagrams_metadata + new_block_diagram_metadata
        self.save_json(all_block_diagrams_metadata, block_diagrams_mappings_file)
        print(f"Saved {len(all_block_diagrams_metadata)} total block diagrams")

        # Merge and save products
        existing_products.update(products)
        
        # Add image metadata to products.json
        existing_products['images'] = all_images_metadata
        
        self.save_json(existing_products, products_file)
        print(f"Saved {len(existing_products)} total products with {len(all_images_metadata)} images")

        # Save markdown file
        self.save_markdown(soup, page_type)

        print(f"\nScraping complete! Data saved to: {self.output_dir}")
        return True


def main():
    parser = argparse.ArgumentParser(
        description='Scrape product data and images from kilointernational.com'
    )
    parser.add_argument('--url', required=True, help='URL to scrape')
    parser.add_argument('--out', required=True, help='Output directory')

    args = parser.parse_args()

    scraper = KiloWebScraper(args.url, args.out)
    success = scraper.scrape()

    sys.exit(0 if success else 1)


if __name__ == '__main__':
    main()
