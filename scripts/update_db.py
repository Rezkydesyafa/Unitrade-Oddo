import json
from db_connection import connect

def update_view():
    conn = connect()
    cur = conn.cursor()

    cur.execute("SELECT arch_db FROM ir_ui_view WHERE key='unitrade_product_ext.unitrade_product_detail_override'")
    res = cur.fetchone()
    if res:
        arch_db_dict = res[0]
        
        with open('d:\\Unitrade_Oddo\\db_view.xml', 'r', encoding='utf-8') as f:
            new_xml = f.read()
            
        arch_db_dict['en_US'] = new_xml
        
        cur.execute("UPDATE ir_ui_view SET arch_db = %s WHERE key='unitrade_product_ext.unitrade_product_detail_override'", (json.dumps(arch_db_dict),))
        conn.commit()
        print("Database updated successfully.")
    else:
        print("Record not found.")

if __name__ == "__main__":
    update_view()
