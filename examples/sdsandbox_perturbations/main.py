# related to open_sbt
from problem.adas_problem import ADASProblem
from evaluation.fitness import *
from evaluation.critical import *
from simulation.simulator import Simulator, SimulationOutput
from model_ga.individual import Individual
from algorithm.nsga2_optimizer import NsgaIIOptimizer
from experiment.search_configuration import DefaultSearchConfiguration

from utils import log_utils
import argparse
from typing import List, Dict, Any, Union
import traceback

from sdsandbox_simulator import SDSandboxSimulator
from examples.models.example_agent import ExampleAgent
from examples.open_sbt.Criticality import FitnessFunction, Criticality

# related to perturbation drive
from perturbationdrive import (
    PerturbationDrive,
    RandomRoadGenerator,
    ScenarioOutcome,
    Scenario,
    CustomRoadGenerator,
)


class SDSandBox_OpenSBTWrapper(Simulator):
    @staticmethod
    def simulate(
        list_individuals: List[Individual],
        variable_names: List[str],
        scenario_path: str,
        sim_time: float,
        time_step: float,
        do_visualize: bool = False,
    ) -> List[SimulationOutput]:
        """
        Runs all indicidual simulations and returns simulation outputs for each individual
        """
        # set up all perturbation drive objects
        simulator = SDSandboxSimulator(
            simulator_exe_path="./examples/sdsandbox_perturbations/sim/donkey-sim.app",
            host="127.0.0.1",
            port=9091,
        )
        ads = ExampleAgent()
        benchmarking_obj = PerturbationDrive(simulator, ads)
        road_generator = CustomRoadGenerator(250)

        # we need to set the sim here up to get the starting position
        benchmarking_obj.simulator.connect()
        starting_pos = benchmarking_obj.simulator.initial_pos

        # create all scenarios
        scenarios: List[Scenario] = [
            SDSandBox_OpenSBTWrapper.individualToScenario(
                individual=ind,
                variable_names=variable_names,
                road_generator=road_generator,
                starting_pos=starting_pos,
            )
            for ind in list_individuals
        ]

        # run the individualts
        outcomes: List[ScenarioOutcome] = benchmarking_obj.simulate_scenarios(
            scenarios=scenarios,
            attention_map={},
            log_dir=None,
            overwrite_logs=False,
            image_size=(240, 320),
        )

        # convert the outcomes to sbt format
        return [
            SimulationOutput(
                simTime=float(len(outcome.frames)),
                times=outcome.frames,
                location={"ego": [(x[0], x[1]) for x in outcome.pos]},
                velocity={
                    "ego": SDSandBox_OpenSBTWrapper._calculate_velocities(
                        outcome.pos, outcome.speeds
                    )
                },
                speed={"ego": outcome.speeds},
                acceleration={"ego": []},
                yaw={
                    "ego": [],
                },
                collisions=[],
                actors={
                    1: "ego",
                },
                otherParams={"xte": outcome.xte},
            )
            for outcome in outcomes
        ]

    @staticmethod
    def individualToScenario(
        individual: Individual,
        variable_names: List[str],
        road_generator: CustomRoadGenerator,
        starting_pos: Tuple[float, float, float],
    ) -> Scenario:
        instance_values = [v for v in zip(variable_names, individual)]
        angles: List[str] = []
        perturbation_scale: int = 0
        perturbation_function_int: int = 1
        perturbation_function: str = ""
        seg_lengths: List[str] = []
        for i in range(0, len(instance_values) + 1):
            # Check if the current item is the perturbation scale
            if instance_values[i][0].startswith("perturbation_scale"):
                perturbation_scale = int(instance_values[i][1])
                break
            elif instance_values[i][0].startswith("perturbation_function"):
                perturbation_function_int = int(instance_values[i][1])
                break
            elif instance_values[i][0].startswith("angle"):
                new_angle = int(instance_values[i][1])
                angles.append(new_angle)
            elif instance_values[i][0].startswith("seg_length"):
                seg_length = int(instance_values[i][1])
                seg_lengths.append(seg_length)

        # generate the road string from the configuration
        seg_lengths: Union[List[str], None] = (
            seg_lengths if len(seg_lengths) > 0 else None
        )
        road_str: str = road_generator.generate(
            starting_pos=starting_pos, angles=angles, seg_lengths=seg_lengths
        )
        # map the function
        amount_keys = len(list(FUNCTION_MAPPING.keys()))
        if perturbation_function_int > 0 and perturbation_function_int <= amount_keys:
            perturbation_function = FUNCTION_MAPPING[perturbation_function_int]
        else:
            perturbation_function = FUNCTION_MAPPING[1]
            print(
                f"Perturbation function not found for values {perturbation_function_int}, using default"
            )

        # return the scenario
        return Scenario(
            waypoints=road_str,
            perturbation_function=perturbation_function,
            perturbation_scale=perturbation_scale,
        )

    @staticmethod
    def _calculate_velocities(
        positions: List[Tuple[float, float, float]], speeds: List[float]
    ) -> Tuple[float, float, float]:
        """
        Calculate velocities given a list of positions and corresponding speeds.
        """
        if len(positions) != len(speeds) or len(speeds) <= 1:
            return []
        velocities = []
        for i in range(len(positions) - 1):
            displacement = np.array(positions[i + 1]) - np.array(positions[i])
            displacement_norm = np.linalg.norm(displacement)
            # avoid division by zero
            if displacement_norm > 0:
                displacement_norm += 0.001
            else:
                displacement_norm -= 0.001
            direction = displacement / displacement_norm
            velocity = direction * speeds[i]
            velocities.append(velocity)

        return velocities


FUNCTION_MAPPING = {
    1: "gaussian_noise",
    2: "poisson_noise",
    3: "impulse_noise",
    4: "defocus_blur",
    5: "glass_blur",
    6: "increase_brightness",
}


def open_sbt():
    # Define search problem
    problem = ADASProblem(
        problem_name="UdacityRoadGenerationProblem",
        scenario_path="",
        xl=[-10, -10, -10, -10, -10, -10, -10, -10, 0, 1],
        xu=[10, 10, 10, 10, 10, 10, 10, 10, 4, 6],
        simulation_variables=[
            "angle1",
            "angle2",
            "angle3",
            "angle4",
            "angle5",
            "angle6",
            "angle7",
            "angle8",
            "perturbation_scale",
            "perturbation_function",
        ],
        fitness_function=FitnessFunction(max_xte=4.0),
        critical_function=Criticality(),
        simulate_function=SDSandBox_OpenSBTWrapper.simulate,
        simulation_time=30,
        sampling_time=0.25,
    )

    log_utils.setup_logging("./log.txt")

    # Set search configuration
    config = DefaultSearchConfiguration()
    config.n_generations = 10
    config.population_size = 2

    # Instantiate search algorithm
    optimizer = NsgaIIOptimizer(problem=problem, config=config)

    # Run search
    res = optimizer.run()

    # Write results
    res.write_results()


def go(
    host: str,
    port: int,
    pert_funcs: List[str] = [],
    attention: Dict[str, Any] = {},
):
    try:
        simulator = SDSandboxSimulator(host=host, port=port)
        ads = ExampleAgent()
        road_generator = RandomRoadGenerator(map_size=250)
        benchmarking_obj = PerturbationDrive(simulator, ads)

        # start the benchmarking
        benchmarking_obj.grid_seach(
            perturbation_functions=pert_funcs,
            attention_map=attention,
            road_generator=road_generator,
            log_dir="./examples/sdsandbox_perturbations/logs.json",
            overwrite_logs=True,
            image_size=(240, 320),  # images are resized to these values
        )
        print(f"{5 * '#'} Finished Running SDSandBox Sim {5 * '#'}")
    except Exception as e:
        print(
            f"{5 * '#'} SDSandBox Error: Exception type: {type(e).__name__}, \nError message: {e}\nTract {traceback.print_exc()} {5 * '#'} "
        )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="SDSandBox Example")

    parser.add_argument("--host", type=str, default="127.0.0.1", help="server sim host")
    parser.add_argument("--port", type=int, default=9091, help="bind to port")
    parser.add_argument(
        "--perturbation",
        dest="perturbation",
        action="append",
        type=str,
        default=[],
        help="perturbations to use on the model. by default all are used",
    )
    parser.add_argument(
        "--attention_map", type=str, default="", help="which attention map to use"
    )
    parser.add_argument(
        "--attention_threshold",
        type=float,
        default=0.5,
        help="threshold for attention map perturbation",
    )
    parser.add_argument(
        "--attention_layer",
        type=str,
        default="conv2d_5",
        help="layer for attention map perturbation",
    )

    args = parser.parse_args()
    attention = (
        {}
        if args.attention_map == ""
        else {
            "map": args.attention_map,
            "threshold": args.attention_threshold,
            "layer": args.attention_layer,
        }
    )

    print(f"{5 * '#'} Started Running SDSandBox Sim {5 * '#'}")
    open_sbt()
    # go(
    #    host=args.host,
    #    port=args.port,
    #    pert_funcs=args.perturbation,
    #    attention=attention,
    # )
