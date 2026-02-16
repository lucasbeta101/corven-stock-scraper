import schedule
import time
import os
from datetime import datetime
import logging
from scraper import CorvenScraper

# Configurar logging SIN emojis para evitar problemas de encoding en Windows
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('scheduler.log', encoding='utf-8'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

def run_scraper():
    """Función que ejecuta el scraper"""
    logger.info("=== INICIANDO SCRAPING PROGRAMADO ===")
    logger.info(f"Timestamp: {datetime.now()}")
    
    try:
        # Crear y ejecutar scraper
        scraper = CorvenScraper()
        success = scraper.run_daily_scrape()
        
        if success:
            logger.info("EXITO: Scraping programado completado exitosamente")
        else:
            logger.error("ERROR: Error en el scraping programado")
            
    except Exception as e:
        logger.error(f"ERROR CRITICO: Error crítico en scraping programado: {str(e)}")

def main():
    """Función principal del scheduler"""
    logger.info("=== SCHEDULER INICIADO ===")
    logger.info(f"Iniciado en: {datetime.now()}")
    
    # Programar ejecución diaria a las 6:00 AM
    schedule.every().day.at("06:00").do(run_scraper)
    
    # También puedes agregar otros horarios si quieres:
    # schedule.every().day.at("18:00").do(run_scraper)  # 6 PM también
    
    logger.info("PROGRAMADO: Scraper programado para ejecutarse diariamente a las 6:00 AM")
    
    # Ejecutar inmediatamente al iniciar (opcional - descomenta si quieres)
    # logger.info("EJECUTANDO: Scraping inicial...")
    # run_scraper()
    
    # Loop principal
    logger.info("MONITOREO: Iniciando loop de monitoreo...")
    while True:
        schedule.run_pending()
        time.sleep(60)  # Revisar cada minuto

if __name__ == "__main__":
    main()