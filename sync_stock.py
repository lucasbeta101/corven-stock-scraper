#!/usr/bin/env python3
"""
Script para sincronizar stock desde products_corven hacia productos
"""
import pymongo
import os
from datetime import datetime
import logging

# Configurar logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

def sync_stock():
    """Sincronizar stock desde products_corven hacia productos"""
    
    try:
        # Conectar a MongoDB
        mongodb_uri = os.getenv('MONGODB_URI')
        if not mongodb_uri:
            raise ValueError("Falta la variable de entorno MONGODB_URI.")
        client = pymongo.MongoClient(mongodb_uri)
        db = client.autopartes
        
        # Colecciones
        productos_collection = db.productos  # Base principal
        corven_collection = db.products_corven  # Datos de stock
        
        logger.info("=== INICIANDO SINCRONIZACIÓN DE STOCK ===")
        
        # Obtener todos los productos de la base principal
        productos = list(productos_collection.find({}, {"codigo": 1, "proveedor": 1}))
        logger.info(f"Productos en base principal: {len(productos)}")
        
        # Crear diccionario de stock de Corven {codigo: stock_status}
        logger.info("Cargando datos de stock de Corven...")
        stock_data = {}
        
        corven_products = corven_collection.find({}, {"code": 1, "stock_status": 1})
        for product in corven_products:
            stock_data[product['code']] = product['stock_status']
        
        logger.info(f"Productos con stock en Corven: {len(stock_data)}")
        
        # Contadores para reporte
        actualizados = 0
        sin_stock = 0
        consultar_stock = 0
        marrose_omitidos = 0
        yokomitsu_omitidos = 0
        
        # Sincronizar cada producto
        for producto in productos:
            codigo = producto['codigo']
            proveedor = producto.get('proveedor', '').lower()
            
            # Buscar stock en datos de Corven
            if codigo in stock_data:
                # Producto encontrado en Corven - actualizar stock
                stock_status = stock_data[codigo]
                
                productos_collection.update_one(
                    {"codigo": codigo},
                    {"$set": {
                        "stock_status": stock_status,
                        "stock_updated_at": datetime.now()
                    }}
                )
                actualizados += 1
                
                if actualizados % 100 == 0:
                    logger.info(f"Actualizados: {actualizados} productos...")
                    
            else:
                # Producto NO encontrado en Corven
                # Si es de Marrose o Yokomitsu, NO marcar como "Sin stock"
                if proveedor == "marrose":
                    marrose_omitidos += 1
                    logger.debug(f"⏭️  Omitiendo producto Marrose: {codigo}")
                elif proveedor == "yokomitsu":
                    yokomitsu_omitidos += 1
                    logger.debug(f"⏭️  Omitiendo producto Yokomitsu: {codigo}")
                else:
                    # Para otros proveedores, marcar consultar stock
                    productos_collection.update_one(
                        {"codigo": codigo},
                        {"$set": {
                            "stock_status": "Consultar stock",
                            "stock_level": "consult",
                            "stock_updated_at": datetime.now()
                        }}
                    )
                    consultar_stock += 1
        
        # Reporte final
        logger.info("=== SINCRONIZACIÓN COMPLETADA ===")
        logger.info(f"✅ Productos actualizados con stock: {actualizados}")
        logger.info(f"❔ Productos marcados 'Consultar stock': {consultar_stock}")
        logger.info(f"🏪 Productos Marrose omitidos: {marrose_omitidos}")
        logger.info(f"🚗 Productos Yokomitsu omitidos: {yokomitsu_omitidos}")
        logger.info(f"📊 Total procesados: {actualizados + consultar_stock + marrose_omitidos + yokomitsu_omitidos}")
        
        # Verificar algunos ejemplos
        logger.info("\n=== VERIFICACIÓN DE EJEMPLOS ===")
        ejemplos = productos_collection.find(
            {"stock_status": {"$exists": True}}, 
            {"codigo": 1, "nombre": 1, "stock_status": 1, "proveedor": 1}
        ).limit(5)
        
        for ejemplo in ejemplos:
            proveedor_info = ejemplo.get('proveedor', 'N/A')
            logger.info(f"📦 {ejemplo['codigo']} ({proveedor_info}): {ejemplo['stock_status']}")
        
        client.close()
        logger.info("✅ Sincronización exitosa")
        return True
        
    except Exception as e:
        logger.error(f"❌ Error en sincronización: {str(e)}")
        return False

if __name__ == "__main__":
    success = sync_stock()
    if not success:
        exit(1)
