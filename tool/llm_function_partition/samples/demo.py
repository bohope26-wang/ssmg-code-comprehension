def process_orders(orders, discount_rate, inventory_client, notifier):
    if not orders:
        raise ValueError("orders is empty")

    normalized_orders = []
    total_amount = 0.0

    for order in orders:
        if order.get("cancelled"):
            continue

        sku = order["sku"].strip().upper()
        quantity = int(order.get("quantity", 0))
        if quantity <= 0:
            print(f"skip invalid quantity for {sku}")
            continue

        stock = inventory_client.lookup(sku)
        if stock < quantity:
            notifier.warn(f"insufficient stock for {sku}")
            break

        base_price = float(order["price"]) * quantity
        discount = base_price * discount_rate if order.get("vip") else 0.0
        final_price = base_price - discount
        normalized_orders.append({"sku": sku, "quantity": quantity, "final_price": round(final_price, 2)})
        total_amount += final_price

    if not normalized_orders:
        return {"saved": 0, "total_amount": 0.0}

    saved_count = inventory_client.persist_batch(normalized_orders)
    notifier.info(f"saved {saved_count} orders")
    return {"saved": saved_count, "total_amount": round(total_amount, 2)}
