import rclpy
from rclpy.node import Node
from tf2_ros import TransformException
from tf2_ros.buffer import Buffer
from tf2_ros.transform_listener import TransformListener

class FrameListener(Node):

    def __init__(self):
        super().__init__('tf_frame_listener')

        # Declare parameters
        # 'target_frame' is the frame we want to know the position OF
        # 'base_frame' is the frame we want to know the position RELATIVE TO
        self.declare_parameter('target_frame', 'camera_link') 
        self.declare_parameter('base_frame', 'base_link')

        self.target_frame = self.get_parameter('target_frame').get_parameter_value().string_value
        self.base_frame = self.get_parameter('base_frame').get_parameter_value().string_value

        # Create the buffer and listener
        # The buffer stores the history of transforms
        self.tf_buffer = Buffer()
        self.tf_listener = TransformListener(self.tf_buffer, self)

        # Create a timer to query the transform periodically (e.g., 10Hz)
        self.timer = self.create_timer(0.1, self.on_timer)

    def on_timer(self):
        # We wrap the lookup in a try-except block because TFs might not be
        # available immediately on startup, or the frames might not exist yet.
        try:
            # lookup_transform(target_frame, source_frame, time)
            # We use rclpy.time.Time() to get the most recent available transform
            t = self.tf_buffer.lookup_transform(
                self.base_frame,      # Coordinate system we want the result in
                self.target_frame,    # The object/link we are tracking
                rclpy.time.Time()
            )

            # Log the position
            self.get_logger().info(
                f'\n--- Transform: {self.target_frame} -> {self.base_frame} ---\n'
                f'Translation: x={t.transform.translation.x:.3f}, '
                f'y={t.transform.translation.y:.3f}, '
                f'z={t.transform.translation.z:.3f}\n'
                f'Rotation:    x={t.transform.rotation.x:.3f}, '
                f'y={t.transform.rotation.y:.3f}, '
                f'z={t.transform.rotation.z:.3f}, '
                f'w={t.transform.rotation.w:.3f}'
            )

        except TransformException as ex:
            self.get_logger().info(
                f'Could not transform {self.target_frame} to {self.base_frame}: {ex}'
            )


def main(args=None):
    rclpy.init(args=args)
    node = FrameListener()
    
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()

if __name__ == '__main__':
    main()