import os
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt

# === Paths ===
project_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
data_folder = os.path.join(project_dir, 'data', 'processed')
os.makedirs(data_folder, exist_ok=True)

# === Years to simulate ===
years = range(2015, 2026)

for year in years:
    merged_csv = os.path.join(data_folder, f'opsd_{year}_merged.csv')
    df = pd.read_csv(merged_csv, parse_dates=['utc_timestamp'], index_col='utc_timestamp')

    # Ensure numeric arrays
    solar_actual = df['DE_solar_generation_actual'].to_numpy(dtype=float)
    wind_actual  = df['DE_wind_onshore_generation_actual'].to_numpy(dtype=float)
    load_actual  = df['DE_load_actual_entsoe_transparency'].to_numpy(dtype=float)

    solar_forecast = df['DE_solar_generation_forecast'].to_numpy(dtype=float)
    wind_forecast  = df['DE_wind_onshore_generation_forecast'].to_numpy(dtype=float)
    load_forecast  = df.get('DE_load_forecast_entsoe_transparency', df['DE_load_actual_entsoe_transparency']).to_numpy(dtype=float)

    df.index = pd.to_datetime(df.index)

    # === Battery parameters ===
    capacity = 50.0  
    soc = 25.0
    p_max = 2.0
    eta = 0.95

    soc_list = []
    grid_load = []

    # === Deterministic MPC (first pass) ===
    for i in range(len(df)):
        solar = float(solar_actual[i])
        wind  = float(wind_actual[i])
        load  = float(load_actual[i])

        net_gen = solar + wind - load

        if net_gen > 0:  # surplus
            charge = min(net_gen, p_max, capacity - soc)
            soc += charge * eta
            net_grid = net_gen - charge
        else:  # deficit
            discharge = min(-net_gen, p_max, soc)
            soc -= discharge / eta
            net_grid = net_gen + discharge

        soc_list.append(soc)
        grid_load.append(net_grid)

    # === Add results ===
    df['soc'] = soc_list
    df['net_grid'] = grid_load

    # === Save simulation results per year in processed folder ===
    output_file = os.path.join(data_folder, f'simulator_results_{year}.csv')
    df.to_csv(output_file)
    print(f"Simulation results saved for {year} in processed folder: {output_file}")

    # === Plot first 3 months for this year ===
    hours_3months = 24 * 90  # 90 days
    df_slice = df.iloc[:hours_3months]

    plt.figure(figsize=(12,6))
    plt.plot(df_slice.index, load_actual[:hours_3months], label='Load')
    plt.plot(df_slice.index, solar_actual[:hours_3months] + wind_actual[:hours_3months], label='Renewable generation')
    plt.plot(soc_list[:hours_3months], label='Battery SoC')
    plt.plot(grid_load[:hours_3months], label='Net grid')
    plt.legend()
    plt.xlabel('Time')
    plt.ylabel('MW / MWh')
    plt.title(f'Deterministic MPC using merged CSV (first 3 months {year})')
    plt.show()