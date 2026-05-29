import os
import pandas as pd
import matplotlib.pyplot as plt


def plot_pressure_drop(history_csv, output_png=None):
    if not os.path.exists(history_csv):
        print(f"⚠ History file not found: {history_csv}")
        return

    df = pd.read_csv(history_csv, skipinitialspace=True)
    df.columns = [c.strip().strip('"') for c in df.columns]

    fig, ax = plt.subplots()
    ax.plot(df['Inner_Iter'], df['pdrop'])

    last_idx = df['pdrop'].last_valid_index()
    if last_idx is not None:
        final_iter = df.loc[last_idx, 'Inner_Iter']
        final_pdrop = df.loc[last_idx, 'pdrop']

        ax.scatter([final_iter], [final_pdrop], color='tab:red', zorder=5)
        ax.annotate(
            f"Final pdrop: {final_pdrop:.4e}",
            xy=(final_iter, final_pdrop),
            xytext=(20, 20),
            textcoords='offset points',
            arrowprops=dict(arrowstyle='->', lw=1.2, color='tab:red'),
            bbox=dict(boxstyle='round,pad=0.3', fc='white', ec='tab:red', alpha=0.9),
            color='tab:red'
        )

    ax.set_xlabel('Inner Iteration')
    ax.set_ylabel('Pressure Drop')
    ax.set_yscale('log')
    ax.set_title('Pressure Drop History')

    if output_png:
        fig.savefig(output_png, dpi=150, bbox_inches='tight')
        print(f"✓ Pressure drop plot saved to {output_png}")
    else:
        plt.show()
    plt.close(fig)

# Called from runWorkflow.py — no standalone execution needed.
