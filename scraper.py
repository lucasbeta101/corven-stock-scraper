import requests
from bs4 import BeautifulSoup
import time
import json
import logging
from datetime import datetime
import pymongo
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.options import Options
import os
from typing import List, Dict, Optional
import re

class CorvenScraper:
    def __init__(self):
        """
        Inicializa el scraper con conexión a tu MongoDB
        """
        self.base_url = "https://e-commerce.corven.com.ar"
        self.login_url = "https://auth.bnssafe.com/realms/autogestion/protocol/openid-connect/auth?client_id=ecommerce_corven_autopartes_backend&response_type=code&redirect_uri=https://e-commerce.corven.com.ar/keycloak_login"
        self.products_url = "https://e-commerce.corven.com.ar/products"
        
        # Credenciales
        self.username = "600732.00"
        self.password = "1234"
        
        # MongoDB setup - CONFIGURADO PARA TU BASE DE DATOS
        mongodb_uri = "mongodb+srv://lucasbeta101:rEeTjUzGt9boy4Zy@bether.qxglnnl.mongodb.net/autopartes"
        self.client = pymongo.MongoClient(mongodb_uri)
        self.db = self.client.autopartes  # Tu base de datos
        self.collection = self.db.products_corven  # Tu nueva colección
        
        # Configurar logging
        logging.basicConfig(
            level=logging.INFO,
            format='%(asctime)s - %(levelname)s - %(message)s',
            handlers=[
                logging.FileHandler('scraper.log'),
                logging.StreamHandler()
            ]
        )
        self.logger = logging.getLogger(__name__)
        
        # Configurar Selenium
        self.driver = None
        self.session = requests.Session()
        
    def setup_driver(self) -> webdriver.Chrome:
        """Configura el driver de Selenium"""
        chrome_options = Options()
        chrome_options.add_argument("--headless")  # Sin interfaz gráfica
        chrome_options.add_argument("--no-sandbox")
        chrome_options.add_argument("--disable-dev-shm-usage")
        chrome_options.add_argument("--disable-gpu")
        chrome_options.add_argument("--window-size=1920,1080")
        chrome_options.add_argument("--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36")
        
        self.driver = webdriver.Chrome(options=chrome_options)
        return self.driver
    
    def login(self) -> bool:
        """Realiza el login usando Selenium"""
        try:
            self.logger.info("Iniciando proceso de login...")
            
            if not self.driver:
                self.setup_driver()
            
            # Ir a la página de login
            self.driver.get(self.login_url)
            time.sleep(3)
            
            # Esperar y encontrar campos de login
            username_field = WebDriverWait(self.driver, 10).until(
                EC.presence_of_element_located((By.ID, "username"))
            )
            password_field = self.driver.find_element(By.ID, "password")
            
            # Ingresar credenciales
            username_field.send_keys(self.username)
            password_field.send_keys(self.password)
            
            # Hacer clic en login
            login_button = self.driver.find_element(By.CSS_SELECTOR, "input[type='submit']")
            login_button.click()
            
            # Esperar redirección
            WebDriverWait(self.driver, 10).until(
                lambda driver: "e-commerce.corven.com.ar" in driver.current_url
            )
            
            # Transferir cookies a requests session
            cookies = self.driver.get_cookies()
            for cookie in cookies:
                self.session.cookies.set(cookie['name'], cookie['value'])
            
            self.logger.info("Login exitoso")
            return True
            
        except Exception as e:
            self.logger.error(f"Error en login: {str(e)}")
            return False
    
    def extract_product_data(self, html: str) -> List[Dict]:
        """Extrae datos de productos del HTML"""
        soup = BeautifulSoup(html, 'html.parser')
        products = []
        
        # Buscar todas las cards de productos
        product_cards = soup.find_all('div', class_='product')
        
        for card in product_cards:
            try:
                # Extraer código del producto
                code_element = card.find('div', class_='info--view-list')
                if not code_element:
                    continue
                
                product_code = code_element.get_text(strip=True)
                
                # Extraer información de stock
                stock_element = card.find('div', class_='product-card__stock')
                stock_status = "Sin información"
                stock_level = "unknown"
                
                if stock_element:
                    stock_text = stock_element.get_text(strip=True)
                    stock_status = stock_text
                    
                    # Determinar nivel de stock (MEJORADO para todos los niveles)
                    if "Stock bajo" in stock_text:
                        stock_level = "low"
                    elif "Sin stock" in stock_text or "Agotado" in stock_text:
                        stock_level = "out_of_stock"
                    elif "Stock disponible" in stock_text or "Stock alto" in stock_text:
                        stock_level = "available"
                    elif "Stock medio" in stock_text:
                        stock_level = "medium"
                    else:
                        stock_level = "unknown"
                        # Log para detectar nuevos niveles
                        self.logger.warning(f"Nuevo nivel de stock detectado: '{stock_text}'")
                
                # Extraer nombre del producto (opcional)
                name_element = card.find('div', class_='product-card__name')
                product_name = ""
                if name_element:
                    name_link = name_element.find('a')
                    if name_link:
                        span = name_link.find('span')
                        if span:
                            product_name = span.get_text(strip=True)
                
                # Extraer marca (opcional)
                brand_element = card.find('div', class_='brand--view-list')
                brand = ""
                if brand_element:
                    brand = brand_element.get_text(strip=True)
                
                product_data = {
                    'code': product_code,
                    'stock_status': stock_status,
                    'stock_level': stock_level,
                    'name': product_name,
                    'brand': brand,
                    'scraped_at': datetime.now(),
                    'page_url': self.products_url
                }
                
                products.append(product_data)
                
            except Exception as e:
                self.logger.warning(f"Error procesando producto: {str(e)}")
                continue
        
        return products
    
    def scrape_page(self, page_number: int) -> List[Dict]:
        """Scrape una página específica usando solo Selenium"""
        try:
            url = f"{self.products_url}?page={page_number}"
            self.logger.info(f"Scrapeando página {page_number}: {url}")
            
            # Usar Selenium en lugar de requests
            if not self.driver:
                self.logger.warning("Driver no disponible, saltando página")
                return []
            
            self.driver.get(url)
            
            # Esperar a que la página cargue completamente
            time.sleep(2)
            
            # Obtener HTML desde Selenium
            html_content = self.driver.page_source
            
            # Extraer productos
            products = self.extract_product_data(html_content)
            
            self.logger.info(f"Extraídos {len(products)} productos de la página {page_number}")
            return products
            
        except Exception as e:
            self.logger.error(f"Error scrapeando página {page_number}: {str(e)}")
            return []
    
    def scrape_all_products(self) -> List[Dict]:
        """Scrape todos los productos (páginas 1-175) usando solo Selenium"""
        all_products = []
        
        # Asegurar que el driver esté disponible
        if not self.driver:
            self.logger.error("Driver no disponible para scraping")
            return []
        
        for page in range(1, 176):  # Páginas 1 a 175
            products = self.scrape_page(page)
            all_products.extend(products)
            
            # Pausa entre requests para evitar rate limiting
            time.sleep(1)
            
            # Log de progreso cada 10 páginas
            if page % 10 == 0:
                self.logger.info(f"Progreso: {page}/175 páginas completadas. Total productos: {len(all_products)}")
        
        return all_products
    
    def save_to_mongodb(self, products: List[Dict]) -> None:
        """Guarda productos en MongoDB usando upsert (actualiza o inserta)"""
        try:
            # Crear índice único en el código del producto
            self.collection.create_index("code", unique=True)
            
            # Insertar/actualizar productos (SOBRESCRIBE en lugar de duplicar)
            for product in products:
                self.collection.update_one(
                    {"code": product["code"]},  # Buscar por código
                    {"$set": product},          # Actualizar todos los campos
                    upsert=True                 # Crear si no existe
                )
            
            self.logger.info(f"Guardados/actualizados {len(products)} productos en MongoDB")
            
        except Exception as e:
            self.logger.error(f"Error guardando en MongoDB: {str(e)}")
    
    def generate_report(self) -> Dict:
        """Genera un reporte del stock actual"""
        try:
            total_products = self.collection.count_documents({})
            
            # Contar por nivel de stock (ACTUALIZADO con todos los niveles)
            stock_counts = {}
            for level in ['low', 'medium', 'available', 'out_of_stock', 'unknown']:
                count = self.collection.count_documents({"stock_level": level})
                stock_counts[level] = count
            
            # Últimos productos actualizados
            last_updated = self.collection.find_one(
                {}, 
                sort=[("scraped_at", pymongo.DESCENDING)]
            )
            
            report = {
                "total_products": total_products,
                "stock_distribution": stock_counts,
                "last_update": last_updated.get("scraped_at") if last_updated else None,
                "generated_at": datetime.now()
            }
            
            return report
            
        except Exception as e:
            self.logger.error(f"Error generando reporte: {str(e)}")
            return {}
    
    def run_daily_scrape(self) -> bool:
        """Ejecuta el scraping diario completo"""
        try:
            self.logger.info("=== INICIANDO SCRAPING DIARIO ===")
            
            # Login
            if not self.login():
                self.logger.error("Fallo en login, abortando scraping")
                return False
            
            # Scraping
            products = self.scrape_all_products()
            
            if not products:
                self.logger.error("No se obtuvieron productos")
                return False
            
            # Guardar en MongoDB
            self.save_to_mongodb(products)
            
            # Generar reporte
            report = self.generate_report()
            self.logger.info(f"Reporte generado: {json.dumps(report, indent=2, default=str)}")
            
            self.logger.info("=== SCRAPING DIARIO COMPLETADO ===")
            return True
            
        except Exception as e:
            self.logger.error(f"Error en scraping diario: {str(e)}")
            return False
        
        finally:
            self.cleanup()
    
    def cleanup(self):
        """Limpia recursos"""
        if self.driver:
            self.driver.quit()
        if self.client:
            self.client.close()

# Función para ejecutar desde línea de comandos
def main():
    # Crear scraper
    scraper = CorvenScraper()
    
    # Ejecutar scraping
    success = scraper.run_daily_scrape()
    
    if success:
        print("Scraping completado exitosamente")
    else:
        print("Error en el scraping")

if __name__ == "__main__":
    main()