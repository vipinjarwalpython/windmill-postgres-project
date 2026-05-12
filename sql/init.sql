-- Beginner-friendly PostgreSQL setup for the orders ETL project.
-- Run this file in your PostgreSQL database before running the pipeline.

DROP TABLE IF EXISTS analytics_orders;
DROP TABLE IF EXISTS orders;

CREATE TABLE orders (
    order_id SERIAL PRIMARY KEY,
    customer_name VARCHAR(100) NOT NULL,
    customer_email VARCHAR(150) NOT NULL,
    product_name VARCHAR(150) NOT NULL,
    category VARCHAR(80) NOT NULL,
    quantity INTEGER NOT NULL CHECK (quantity > 0),
    unit_price NUMERIC(10, 2) NOT NULL CHECK (unit_price >= 0),
    order_status VARCHAR(30) NOT NULL,
    order_date DATE NOT NULL,
    shipping_city VARCHAR(100) NOT NULL,
    payment_method VARCHAR(50) NOT NULL
);

INSERT INTO orders (
    customer_name,
    customer_email,
    product_name,
    category,
    quantity,
    unit_price,
    order_status,
    order_date,
    shipping_city,
    payment_method
) VALUES
    ('Aarav Sharma', 'aarav.sharma@example.com', 'Wireless Mouse', 'Electronics', 2, 799.00, 'delivered', '2026-05-01', 'Bengaluru', 'UPI'),
    ('Priya Nair', 'priya.nair@example.com', 'Cotton Kurta', 'Fashion', 1, 1299.00, 'delivered', '2026-05-02', 'Kochi', 'Credit Card'),
    ('Rahul Mehta', 'rahul.mehta@example.com', 'Bluetooth Speaker', 'Electronics', 1, 2499.00, 'shipped', '2026-05-03', 'Mumbai', 'Debit Card'),
    ('Sneha Iyer', 'sneha.iyer@example.com', 'Yoga Mat', 'Fitness', 3, 699.00, 'delivered', '2026-05-03', 'Chennai', 'UPI'),
    ('Kabir Khan', 'kabir.khan@example.com', 'Office Chair', 'Furniture', 1, 7499.00, 'processing', '2026-05-04', 'Delhi', 'Net Banking'),
    ('Meera Joshi', 'meera.joshi@example.com', 'Stainless Steel Bottle', 'Home & Kitchen', 4, 399.00, 'delivered', '2026-05-05', 'Pune', 'UPI'),
    ('Vikram Rao', 'vikram.rao@example.com', 'Running Shoes', 'Footwear', 1, 3199.00, 'cancelled', '2026-05-05', 'Hyderabad', 'Credit Card'),
    ('Ananya Das', 'ananya.das@example.com', 'LED Desk Lamp', 'Home & Kitchen', 2, 1199.00, 'shipped', '2026-05-06', 'Kolkata', 'Debit Card'),
    ('Ishaan Patel', 'ishaan.patel@example.com', 'Laptop Backpack', 'Accessories', 1, 1899.00, 'delivered', '2026-05-07', 'Ahmedabad', 'UPI'),
    ('Neha Verma', 'neha.verma@example.com', 'Noise Cancelling Headphones', 'Electronics', 1, 8999.00, 'delivered', '2026-05-08', 'Jaipur', 'Credit Card');

CREATE TABLE analytics_orders (
    analytics_id SERIAL PRIMARY KEY,
    order_id INTEGER NOT NULL,
    customer_name VARCHAR(100) NOT NULL,
    customer_email VARCHAR(150) NOT NULL,
    product_name VARCHAR(150) NOT NULL,
    category VARCHAR(80) NOT NULL,
    quantity INTEGER NOT NULL,
    unit_price NUMERIC(10, 2) NOT NULL,
    order_amount NUMERIC(10, 2) NOT NULL,
    gst_amount NUMERIC(10, 2) NOT NULL,
    final_amount NUMERIC(10, 2) NOT NULL,
    order_status VARCHAR(30) NOT NULL,
    order_date DATE NOT NULL,
    shipping_city VARCHAR(100) NOT NULL,
    payment_method VARCHAR(50) NOT NULL,
    loaded_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_analytics_orders_order_date ON analytics_orders(order_date);
CREATE INDEX idx_analytics_orders_category ON analytics_orders(category);
